// Package supervisor starts and watches the processes 556d owns (each companion's hermes
// gateway, the embedder, later TTS/image services). Children are placed in a kill-on-close job
// so they die with the daemon; a crashed child restarts with backoff; readiness is observed
// through an HTTP health URL. A spec may provide a graceful Stop (ask the child to finish on
// its own) with a Grace period before the kill — a companion's in-flight memory write lands.
package supervisor

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/exec"
	"sync"
	"time"
)

type Spec struct {
	Name   string
	Exe    string
	Args   []string
	Env    []string // extra KEY=VALUE entries appended to the daemon's environment
	Dir    string
	Health string // GET URL expected to return 2xx when ready; "" = no probe
	// Stop asks the child to exit by itself (e.g. Hermes's planned-stop marker). When it returns
	// true the supervisor waits up to Grace for the exit before killing; nil/false = kill at once.
	Stop  func(cmd *exec.Cmd) bool
	Grace time.Duration
}

type child struct {
	cmd    *exec.Cmd
	spec   Spec
	exited chan struct{} // closed once the process has exited
}

type Supervisor struct {
	job     jobHandle
	wg      sync.WaitGroup
	mu      sync.Mutex
	running map[string]*child
}

func New() (*Supervisor, error) {
	j, err := newJob()
	if err != nil {
		return nil, err
	}
	return &Supervisor{job: j, running: map[string]*child{}}, nil
}

// Restart ends the named child (gracefully when its spec allows); its run loop brings it back.
func (s *Supervisor) Restart(name string) error {
	s.mu.Lock()
	c := s.running[name]
	s.mu.Unlock()
	if c == nil || c.cmd.Process == nil {
		return fmt.Errorf("%s is not running", name)
	}
	log.Printf("[%s] restart requested", name)
	go s.terminate(c, "restart")
	return nil
}

// terminate ends a child: the graceful request first when the spec has one, a kill after Grace.
func (s *Supervisor) terminate(c *child, why string) {
	if c.spec.Stop != nil && c.spec.Grace > 0 && c.spec.Stop(c.cmd) {
		log.Printf("[%s] %s: asked to finish up (up to %s)", c.spec.Name, why, c.spec.Grace)
		select {
		case <-c.exited:
			return
		case <-time.After(c.spec.Grace):
			log.Printf("[%s] still running after %s; killing", c.spec.Name, c.spec.Grace)
		}
	}
	_ = c.cmd.Process.Kill()
	<-c.exited
}

// Run starts the spec and keeps it alive until ctx is cancelled. The returned channel closes
// once the child has exited for good (after a graceful stop or the kill).
func (s *Supervisor) Run(ctx context.Context, spec Spec) <-chan struct{} {
	finished := make(chan struct{})
	s.wg.Add(1)
	go func() {
		defer close(finished)
		defer s.wg.Done()
		backoff := time.Second
		for {
			start := time.Now()
			err := s.runOnce(ctx, spec)
			if ctx.Err() != nil {
				return
			}
			if time.Since(start) > 30*time.Second {
				backoff = time.Second // a healthy run resets the backoff
			}
			log.Printf("[%s] exited (%v); restarting in %s", spec.Name, err, backoff)
			select {
			case <-time.After(backoff):
			case <-ctx.Done():
				return
			}
			if backoff < 30*time.Second {
				backoff *= 2
			}
		}
	}()
	return finished
}

func (s *Supervisor) runOnce(ctx context.Context, spec Spec) error {
	cmd := exec.Command(spec.Exe, spec.Args...)
	cmd.Dir = spec.Dir
	cmd.Env = append(os.Environ(), spec.Env...)
	cmd.Stdout = prefixWriter(spec.Name)
	cmd.Stderr = prefixWriter(spec.Name)
	if err := cmd.Start(); err != nil {
		return fmt.Errorf("start: %w", err)
	}
	if err := s.job.assign(cmd); err != nil {
		log.Printf("[%s] job assign failed: %v", spec.Name, err)
	}
	log.Printf("[%s] started pid %d", spec.Name, cmd.Process.Pid)
	c := &child{cmd: cmd, spec: spec, exited: make(chan struct{})}
	s.mu.Lock()
	s.running[spec.Name] = c
	s.mu.Unlock()
	defer func() {
		s.mu.Lock()
		if s.running[spec.Name] == c {
			delete(s.running, spec.Name)
		}
		s.mu.Unlock()
	}()

	done := make(chan error, 1)
	go func() {
		err := cmd.Wait()
		done <- err
		close(c.exited)
	}()

	if spec.Health != "" {
		go probe(ctx, spec)
	}
	select {
	case err := <-done:
		return err
	case <-ctx.Done():
		s.terminate(c, "stop")
		return ctx.Err()
	}
}

func probe(ctx context.Context, spec Spec) {
	client := &http.Client{Timeout: 2 * time.Second}
	deadline := time.Now().Add(120 * time.Second)
	for time.Now().Before(deadline) {
		select {
		case <-ctx.Done():
			return
		case <-time.After(time.Second):
		}
		resp, err := client.Get(spec.Health)
		if err == nil {
			resp.Body.Close()
			if resp.StatusCode < 300 {
				log.Printf("[%s] ready (%s)", spec.Name, spec.Health)
				return
			}
		}
	}
	log.Printf("[%s] not ready after 120s", spec.Name)
}

// Wait blocks until every child goroutine has finished (call after cancelling ctx).
func (s *Supervisor) Wait() {
	s.wg.Wait()
	s.job.close()
}

type prefixWriter string

func (p prefixWriter) Write(b []byte) (int, error) {
	log.Printf("[%s] %s", string(p), trimNL(b))
	return len(b), nil
}

func trimNL(b []byte) string {
	for len(b) > 0 && (b[len(b)-1] == '\n' || b[len(b)-1] == '\r') {
		b = b[:len(b)-1]
	}
	return string(b)
}
