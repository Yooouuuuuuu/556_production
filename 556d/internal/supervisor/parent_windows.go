//go:build windows

package supervisor

import (
	"log"
	"os"

	"golang.org/x/sys/windows"
)

// WatchParent runs onExit when the given parent process ends. The app that spawns 556d passes
// its own pid, so a crashed or force-killed app never leaves the backend behind: onExit starts
// the daemon's shutdown (companions finish up, then the job object reaps the rest).
func WatchParent(pid int, onExit func()) {
	if pid <= 0 {
		return
	}
	h, err := windows.OpenProcess(windows.SYNCHRONIZE, false, uint32(pid))
	if err != nil {
		log.Printf("[parent] cannot open pid %d: %v", pid, err)
		return
	}
	go func() {
		_, _ = windows.WaitForSingleObject(h, windows.INFINITE)
		log.Printf("[parent] pid %d exited; shutting down", pid)
		if onExit != nil {
			onExit()
			return
		}
		os.Exit(0) // job object (kill-on-close) terminates the children
	}()
}
