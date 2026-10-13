// 556d — the agency daemon. S1 scope: supervise hermes serve and the embedder sidecar.
package main

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"flag"
	"fmt"
	"log"
	"os"
	"os/signal"
	"syscall"

	"net/http"

	"github.com/Yooouuuuuuu/556_production/556d/internal/api"
	"github.com/Yooouuuuuuu/556_production/556d/internal/bridge"
	"github.com/Yooouuuuuuu/556_production/556d/internal/config"
	"github.com/Yooouuuuuuu/556_production/556d/internal/hermes"
	"github.com/Yooouuuuuuu/556_production/556d/internal/shim"
	"github.com/Yooouuuuuuu/556_production/556d/internal/supervisor"
)

func main() {
	cfgPath := flag.String("config", "556d.toml", "path to 556d.toml")
	parentPID := flag.Int("parent-pid", 0, "exit when this process ends (set by the desktop app)")
	flag.Parse()
	log.SetFlags(log.Ltime)
	supervisor.WatchParent(*parentPID)

	cfg, err := config.Load(*cfgPath)
	if err != nil {
		log.Fatal(err)
	}
	token := cfg.Hermes.Token
	if token == "" {
		b := make([]byte, 24)
		_, _ = rand.Read(b)
		token = hex.EncodeToString(b)
	}

	sup, err := supervisor.New()
	if err != nil {
		log.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	sup.Run(ctx, supervisor.Spec{
		Name: "hermes",
		Exe:  cfg.Hermes.Exe,
		Args: []string{"serve", "--skip-build", "--host", "127.0.0.1", "--port", fmt.Sprint(cfg.Hermes.Port)},
		Env: []string{
			"HERMES_HOME=" + cfg.Hermes.Home,
			"HERMES_DESKTOP=1",
			"HERMES_DASHBOARD_SESSION_TOKEN=" + token,
		},
		Dir:    cfg.Root,
		Health: fmt.Sprintf("http://127.0.0.1:%d/api/health", cfg.Hermes.Port),
	})
	if cfg.Embedder.Enabled {
		sup.Run(ctx, supervisor.Spec{
			Name: "embedder",
			Exe:  cfg.Embedder.Exe,
			Args: []string{"-m", cfg.Embedder.Model, "--embedding", "--pooling", "cls", "-c", "8192",
				"--host", "127.0.0.1", "--port", fmt.Sprint(cfg.Embedder.Port)},
			Dir:    cfg.Root,
			Health: fmt.Sprintf("http://127.0.0.1:%d/health", cfg.Embedder.Port),
		})
	}
	if len(cfg.Shim.Backends) > 0 {
		go func() {
			if err := shim.New(cfg.Shim).ListenAndServe(ctx); err != nil {
				log.Printf("[shim] server error: %v", err)
			}
		}()
	}
	// daemon port: avatar bridge (API + /ws + static) + the chat API backed by hermes serve
	mux := http.NewServeMux()
	br := bridge.New(cfg.Bridge)
	br.Register(mux)
	hc := hermes.New("127.0.0.1", cfg.Hermes.Port, token)
	go func() {
		if err := hc.Connect(ctx); err != nil && ctx.Err() == nil {
			log.Printf("[hermes] %v", err)
		}
	}()
	api.New(hc, br, sup, cfg.Daemon.Profile, cfg.Hermes.Home).Register(mux)
	daemonSrv := &http.Server{Addr: fmt.Sprintf("127.0.0.1:%d", cfg.Daemon.Port), Handler: mux}
	go func() {
		log.Printf("[daemon] listening on :%d (bridge)", cfg.Daemon.Port)
		if err := daemonSrv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Printf("[daemon] server error: %v", err)
		}
	}()
	log.Printf("556d up: hermes :%d (token %s...), embedder :%d, shim :%d, bridge :%d - Ctrl+C to stop",
		cfg.Hermes.Port, token[:6], cfg.Embedder.Port, cfg.Shim.Port, cfg.Daemon.Port)

	sig := make(chan os.Signal, 1)
	signal.Notify(sig, os.Interrupt, syscall.SIGTERM)
	<-sig
	log.Print("shutting down")
	_ = daemonSrv.Close()
	cancel()
	sup.Wait()
}
