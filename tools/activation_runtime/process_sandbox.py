"""Linux default-deny seccomp and resource sandbox; unsupported hosts refuse."""
import ctypes
import errno
import resource

def sandbox(cpu,memory):
    resource.setrlimit(resource.RLIMIT_CPU,(cpu,cpu))
    resource.setrlimit(resource.RLIMIT_AS,(memory,memory))
    resource.setrlimit(resource.RLIMIT_FSIZE,(0,0))
    resource.setrlimit(resource.RLIMIT_NOFILE,(16,16))
    lib=ctypes.CDLL("libseccomp.so.2",use_errno=True)
    lib.seccomp_init.argtypes=[ctypes.c_uint32];lib.seccomp_init.restype=ctypes.c_void_p
    lib.seccomp_syscall_resolve_name.argtypes=[ctypes.c_char_p];lib.seccomp_syscall_resolve_name.restype=ctypes.c_int
    lib.seccomp_rule_add.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_int,ctypes.c_uint];lib.seccomp_rule_add.restype=ctypes.c_int
    lib.seccomp_load.argtypes=[ctypes.c_void_p];lib.seccomp_load.restype=ctypes.c_int
    lib.seccomp_release.argtypes=[ctypes.c_void_p]
    # Default deny; only pipe I/O, memory management, time and process exit allowed.
    ctx=lib.seccomp_init(0x00050000|errno.EPERM)
    if not ctx:raise RuntimeError("Sandbox initialization failed")
    allowed=("read","write","readv","writev","close","fstat","newfstatat","lseek","fcntl",
             "brk","mmap","mprotect","munmap","mremap","madvise","rt_sigaction",
             "rt_sigprocmask","rt_sigreturn","sigaltstack","clock_gettime","gettimeofday",
             "getpid","gettid","futex","sched_yield","getrandom","getrusage","exit","exit_group")
    for name in allowed:
        number=lib.seccomp_syscall_resolve_name(name.encode())
        if number>=0 and lib.seccomp_rule_add(ctx,0x7fff0000,number,0)!=0:raise RuntimeError("Sandbox rule failure")
    if lib.seccomp_load(ctx)!=0:raise RuntimeError("Sandbox installation refused")
    lib.seccomp_release(ctx)

