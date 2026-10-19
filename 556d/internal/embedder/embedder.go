// Package embedder runs the local embedding server when 設定 → 模型連線 says the vectors are made here
// (llama-server with a GGUF file), and stands down when they come from an endpoint elsewhere.
package embedder

import (
	"context"
	"fmt"
	"path/filepath"
	"sync"

	"github.com/Yooouuuuuuu/556_production/556d/internal/models"
	"github.com/Yooouuuuuuu/556_production/556d/internal/supervisor"
)

type Ctl struct {
	parent context.Context
	sup    *supervisor.Supervisor
	root   string
	mu     sync.Mutex
	cur    models.Embedder
	cancel context.CancelFunc
	done   <-chan struct{}
}

func New(parent context.Context, sup *supervisor.Supervisor, root string) *Ctl {
	return &Ctl{parent: parent, sup: sup, root: root}
}

func (c *Ctl) resolve(p string) string {
	if p == "" || filepath.IsAbs(p) {
		return p
	}
	return filepath.Join(c.root, filepath.FromSlash(p))
}

// Apply makes the running state match the setting: start (or restart on a change) the local server for
// kind llama, stop it for anything else. Idempotent.
func (c *Ctl) Apply(e models.Embedder) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if e.Kind != models.EmbedLlama {
		c.stopLocked()
		c.cur = e
		return
	}
	if c.cancel != nil && c.cur.Exe == e.Exe && c.cur.File == e.File && c.cur.Port == e.Port {
		return
	}
	c.stopLocked()
	ctx, cancel := context.WithCancel(c.parent)
	c.cancel = cancel
	c.cur = e
	c.done = c.sup.Run(ctx, supervisor.Spec{
		Name: "embedder",
		Exe:  c.resolve(e.Exe),
		Args: []string{"-m", c.resolve(e.File), "--embedding", "--pooling", "cls", "-c", "8192",
			"--host", "127.0.0.1", "--port", fmt.Sprint(e.Port)},
		Dir:    c.root,
		Health: fmt.Sprintf("http://127.0.0.1:%d/health", e.Port),
	})
}

func (c *Ctl) Stop() {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.stopLocked()
}

func (c *Ctl) stopLocked() {
	if c.cancel == nil {
		return
	}
	c.cancel()
	<-c.done
	c.cancel, c.done = nil, nil
}

// Status for the settings page: what runs locally, if anything.
func (c *Ctl) Status() map[string]any {
	c.mu.Lock()
	defer c.mu.Unlock()
	return map[string]any{"kind": c.cur.Kind, "local_running": c.cancel != nil, "port": c.cur.Port}
}
