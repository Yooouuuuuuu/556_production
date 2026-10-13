//go:build !windows

package supervisor

import "os/exec"

// Non-Windows: no job object yet; children are killed explicitly on shutdown.
type jobHandle struct{}

func newJob() (jobHandle, error)         { return jobHandle{}, nil }
func (jobHandle) assign(*exec.Cmd) error { return nil }
func (jobHandle) close()                 {}
