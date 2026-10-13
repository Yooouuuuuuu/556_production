// Package supervisor starts and watches the sidecar processes 556d owns (hermes serve,
// the embedder, later TTS/image services). Children are placed in a kill-on-close job so
// they die with the daemon; a crashed child restarts with backoff; readiness is observed
// through an HTTP health URL.
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
}

type Supervisor struct {
	job jobHandle
	wg  sync.WaitGroup
}

func New() (*Supervisor, error) {
	j, err := newJob()
	if err != nil {
		return nil, err
	}
	return &Supervisor{job: j}, nil
}

// Run starts the spec and keeps it alive until ctx is cancelled.
func (s *Supervisor) Run(ctx context.Context, spec Spec) {
	s.wg.Add(1)
	go func() {
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

	done := make(chan error, 1)
	go func() { done <- cmd.Wait() }()

	if spec.Health != "" {
		go probe(ctx, spec)
	}
	select {
	case err := <-done:
		return err
	case <-ctx.Done():
		_ = cmd.Process.Kill()
		<-done
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
