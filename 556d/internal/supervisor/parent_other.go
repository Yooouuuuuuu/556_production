//go:build !windows

package supervisor

// WatchParent is a no-op off Windows for now.
func WatchParent(pid int, onExit func()) {}
