// 556d — the agency daemon. S1 scope: supervise hermes serve and the embedder sidecar.
package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"

	"net/http"

	"github.com/Yooouuuuuuu/556_production/556d/internal/api"
	"github.com/Yooouuuuuuu/556_production/556d/internal/bridge"
	"github.com/Yooouuuuuuu/556_production/556d/internal/companions"
	"github.com/Yooouuuuuuu/556_production/556d/internal/config"
	"github.com/Yooouuuuuuu/556_production/556d/internal/shim"
	"github.com/Yooouuuuuuu/556_production/556d/internal/supervisor"
)

func main() {
	cfgPath := flag.String("config", "556d.toml", "path to 556d.toml")
	parentPID := flag.Int("parent-pid", 0, "exit when this process ends (set by the desktop app)")
	noHermes := flag.Bool("no-hermes", false, "do not spawn hermes serve: shim + embedder + API only (CLI tests, harnesses)")
	flag.Parse()
	log.SetFlags(log.Ltime)

	cfg, err := config.Load(*cfgPath)
	if err != nil {
		log.Fatal(err)
	}

	sup, err := supervisor.New()
	if err != nil {
		log.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// One way down for everything: the app's POST /api/shutdown, the parent watcher and Ctrl+C all
	// request a shutdown; companions get their grace period (memory writes land), then the job closes.
	if *parentPID > 0 {
		supervisor.WatchParent(*parentPID, func() {
			requestShutdown()
			time.AfterFunc(90*time.Second, func() { os.Exit(0) }) // backstop if a companion will not finish
		})
	}

	// Companions (home/profiles/<name>) start only when you start them from the roster;
	// nothing auto-starts (DECISIONS 2026-10-02). -no-hermes is kept for old launchers (no-op).
	if *noHermes {
		log.Printf("[556d] -no-hermes is now the default behaviour (companions start from the roster)")
	}
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
	mgr := companions.New(ctx, cfg.Hermes.Home, cfg.Hermes.Exe, cfg.Root, sup)
	hub := api.New(mgr, br, sup, cfg.Hermes.Home, cfg.Daemon.Profile)
	hub.Shutdown = requestShutdown
	hub.Register(mux)
	daemonSrv := &http.Server{Addr: fmt.Sprintf("127.0.0.1:%d", cfg.Daemon.Port), Handler: mux}
	go func() {
		log.Printf("[daemon] listening on :%d (bridge)", cfg.Daemon.Port)
		if err := daemonSrv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Printf("[daemon] server error: %v", err)
		}
	}()
	log.Printf("556d up: %d companion(s) on the roster, embedder :%d, shim :%d, bridge :%d - Ctrl+C to stop",
		len(mgr.List()), cfg.Embedder.Port, cfg.Shim.Port, cfg.Daemon.Port)

	sig := make(chan os.Signal, 1)
	signal.Notify(sig, os.Interrupt, syscall.SIGTERM)
	select {
	case <-sig:
	case <-shutdownReq:
	}
	log.Print("shutting down: companions finish up first")
	mgr.StopAll() // graceful: planned-stop marker, grace period, then kill
	_ = daemonSrv.Close()
	cancel()
	sup.Wait()
	log.Print("556d down")
}

var shutdownReq = make(chan struct{}, 1)

// requestShutdown asks main to run the shutdown sequence (idempotent).
func requestShutdown() {
	select {
	case shutdownReq <- struct{}{}:
	default:
	}
}
