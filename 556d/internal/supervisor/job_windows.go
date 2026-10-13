//go:build windows

package supervisor

import (
	"os/exec"
	"unsafe"

	"golang.org/x/sys/windows"
)

// jobHandle wraps a Windows job object with KILL_ON_JOB_CLOSE: when 556d exits for any
// reason the OS terminates every child we assigned — no orphaned hermes/llama processes.
type jobHandle struct{ h windows.Handle }

func newJob() (jobHandle, error) {
	h, err := windows.CreateJobObject(nil, nil)
	if err != nil {
		return jobHandle{}, err
	}
	info := windows.JOBOBJECT_EXTENDED_LIMIT_INFORMATION{}
	info.BasicLimitInformation.LimitFlags = windows.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
	_, err = windows.SetInformationJobObject(h, windows.JobObjectExtendedLimitInformation,
		uintptr(unsafe.Pointer(&info)), uint32(unsafe.Sizeof(info)))
	if err != nil {
		windows.CloseHandle(h)
		return jobHandle{}, err
	}
	return jobHandle{h: h}, nil
}

func (j jobHandle) assign(cmd *exec.Cmd) error {
	p, err := windows.OpenProcess(windows.PROCESS_SET_QUOTA|windows.PROCESS_TERMINATE, false, uint32(cmd.Process.Pid))
	if err != nil {
		return err
	}
	defer windows.CloseHandle(p)
	return windows.AssignProcessToJobObject(j.h, p)
}

func (j jobHandle) close() {
	if j.h != 0 {
		windows.CloseHandle(j.h)
	}
}
