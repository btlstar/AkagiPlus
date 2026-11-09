//! Own external helpers even when the application exits without draining Tokio tasks.
use std::{
    io,
    os::windows::io::{AsRawHandle, FromRawHandle, OwnedHandle},
};
use tokio::process::Child;
use windows_sys::Win32::System::JobObjects::{
    AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation,
    SetInformationJobObject, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
};

pub struct Job {
    _handle: OwnedHandle,
}
impl Job {
    pub fn attach(child: &Child) -> io::Result<Self> {
        // The unnamed handle is not inheritable; only this application owns it.
        let raw = unsafe { CreateJobObjectW(std::ptr::null(), std::ptr::null()) };
        if raw.is_null() {
            return Err(io::Error::last_os_error());
        }
        // SAFETY: CreateJobObjectW returned a new, valid handle owned by this scope.
        let handle = unsafe { OwnedHandle::from_raw_handle(raw) };
        let mut limits = JOBOBJECT_EXTENDED_LIMIT_INFORMATION::default();
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        // SAFETY: the pointer and size describe a live, correctly typed information buffer.
        if unsafe {
            SetInformationJobObject(
                handle.as_raw_handle(),
                JobObjectExtendedLimitInformation,
                (&limits as *const JOBOBJECT_EXTENDED_LIMIT_INFORMATION).cast(),
                std::mem::size_of_val(&limits) as u32,
            )
        } == 0
        {
            return Err(io::Error::last_os_error());
        }
        let process = child.raw_handle().ok_or_else(|| {
            io::Error::new(io::ErrorKind::NotFound, "external helper already exited")
        })?;
        // SAFETY: both handles remain valid for this call. Only our newly spawned child
        // is attached; existing user processes are never adopted into this job.
        if unsafe { AssignProcessToJobObject(handle.as_raw_handle(), process) } == 0 {
            return Err(io::Error::last_os_error());
        }
        Ok(Self { _handle: handle })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{process::Stdio, time::Duration};
    #[tokio::test]
    async fn closing_owner_terminates_helper() {
        let mut child = tokio::process::Command::new("powershell.exe")
            .args([
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "Start-Sleep -Seconds 60",
            ])
            .creation_flags(0x08000000)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .kill_on_drop(true)
            .spawn()
            .expect("start test helper");
        let job = Job::attach(&child).expect("own test helper");
        assert!(child.try_wait().expect("query live helper").is_none());
        drop(job);
        tokio::time::timeout(Duration::from_secs(5), child.wait())
            .await
            .expect("helper must exit when its owner closes")
            .expect("reap test helper");
        // Windows job closure may report exit code zero; prompt exit is the contract.
    }
}
