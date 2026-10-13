// Package config loads 556d.toml. Relative paths resolve against the directory that
// contains the config file (the repo root).
package config

import (
	"fmt"
	"os"
	"path/filepath"

	"github.com/BurntSushi/toml"

	"github.com/Yooouuuuuuu/556_production/556d/internal/bridge"
	"github.com/Yooouuuuuuu/556_production/556d/internal/shim"
)

type Config struct {
	Root     string        `toml:"-"`
	Daemon   Daemon        `toml:"daemon"`
	Hermes   Hermes        `toml:"hermes"`
	Embedder Embedder      `toml:"embedder"`
	Shim     shim.Config   `toml:"shim"`
	Bridge   bridge.Config `toml:"bridge"`
}

type Daemon struct {
	Port       int    `toml:"port"`
	Profile    string `toml:"profile"`      // Hermes profile for the chat API ("" = home's default companion)
	WebChatDir string `toml:"web_chat_dir"` // static web-chat SPA, served at /chat/
}

type Hermes struct {
	Home  string `toml:"home"`
	Exe   string `toml:"exe"`
	Port  int    `toml:"port"`
	Token string `toml:"token"` // empty = generated per start
}

type Embedder struct {
	Enabled bool   `toml:"enabled"`
	Exe     string `toml:"exe"`
	Model   string `toml:"model"`
	Port    int    `toml:"port"`
}

func Load(path string) (*Config, error) {
	c := &Config{
		Daemon:   Daemon{Port: 55600},
		Hermes:   Hermes{Home: "home", Exe: "vendor/hermes-agent/.venv/Scripts/hermes.exe", Port: 55610},
		Embedder: Embedder{Enabled: true, Exe: "bin/llama/llama-server.exe", Model: "models/bge-m3-Q8_0.gguf", Port: 18768},
	}
	if _, err := toml.DecodeFile(path, c); err != nil {
		return nil, fmt.Errorf("config %s: %w", path, err)
	}
	abs, err := filepath.Abs(path)
	if err != nil {
		return nil, err
	}
	c.Root = filepath.Dir(abs)
	c.Hermes.Home = c.resolve(c.Hermes.Home)
	c.Hermes.Exe = c.resolve(c.Hermes.Exe)
	c.Embedder.Exe = c.resolve(c.Embedder.Exe)
	c.Embedder.Model = c.resolve(c.Embedder.Model)
	if c.Shim.Port == 0 {
		c.Shim.Port = 55601
	}
	if c.Shim.RoutingFile == "" {
		c.Shim.RoutingFile = "shim/routing.json"
	}
	c.Shim.RoutingFile = c.resolve(c.Shim.RoutingFile)
	if c.Daemon.WebChatDir == "" {
		c.Daemon.WebChatDir = "ui/web-chat"
	}
	c.Daemon.WebChatDir = c.resolve(c.Daemon.WebChatDir)
	if c.Bridge.StaticDir == "" {
		c.Bridge.StaticDir = "ui/live2d"
	}
	if c.Bridge.AssetsDir == "" {
		c.Bridge.AssetsDir = "assets/live2d"
	}
	if c.Bridge.VendorDir == "" {
		c.Bridge.VendorDir = "vendor/live2d"
	}
	if c.Bridge.AudioCache == "" {
		c.Bridge.AudioCache = "home/audio_cache"
	}
	c.Bridge.StaticDir = c.resolve(c.Bridge.StaticDir)
	c.Bridge.AssetsDir = c.resolve(c.Bridge.AssetsDir)
	c.Bridge.VendorDir = c.resolve(c.Bridge.VendorDir)
	c.Bridge.AudioCache = c.resolve(c.Bridge.AudioCache)
	if _, err := os.Stat(c.Hermes.Exe); err != nil {
		return nil, fmt.Errorf("hermes exe not found: %s (run setup-vendor.ps1)", c.Hermes.Exe)
	}
	return c, nil
}

func (c *Config) resolve(p string) string {
	if filepath.IsAbs(p) {
		return p
	}
	return filepath.Join(c.Root, filepath.FromSlash(p))
}
