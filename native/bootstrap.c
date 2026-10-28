#define WIN32_LEAN_AND_MEAN
#include <windows.h>

/* Only initialization of paths/environment occurs at attach. Loading the real
 * library and creating the companion are deferred until a normal DWM call. */
static HMODULE self_module;
static HMODULE real_dwm;
static INIT_ONCE once = INIT_ONCE_STATIC_INIT;
static WCHAR game_root[32768];
static const char identity[] = "LLLUCKY_BOOTSTRAP_2_1";

static BOOL copy_text(WCHAR *out, DWORD capacity, const WCHAR *text) {
    DWORD i=0;
    while (text[i]) { if(i+1>=capacity)return FALSE;out[i]=text[i];++i; }
    out[i]=0;return TRUE;
}
static BOOL append_text(WCHAR *out,DWORD capacity,const WCHAR *text) {
    DWORD n=0;while(out[n])++n;
    return copy_text(out+n,capacity-n,text);
}
static BOOL same_ascii(const WCHAR *a,const WCHAR *b) {
    while(*a && *b) {
        WCHAR x=*a++,y=*b++;
        if(x>=L'A' && x<=L'Z')x+=L'a'-L'A';
        if(y>=L'A' && y<=L'Z')y+=L'a'-L'A';
        if(x!=y)return FALSE;
    }
    return !*a && !*b;
}
static BOOL is_game(void) {
    WCHAR exe[32768];DWORD n=GetModuleFileNameW(NULL,exe,32768),i;
    if(!n || n>=32768)return FALSE;
    i=n;while(i && exe[i-1]!=L'\\' && exe[i-1]!=L'/')--i;
    return same_ascii(exe+i,L"AzerothSurvivors.exe");
}
static BOOL root_path(WCHAR *out,DWORD capacity,const WCHAR *suffix) {
    return copy_text(out,capacity,game_root) && append_text(out,capacity,suffix);
}
static void log_line(const char *text) {
    WCHAR path[32768];DWORD written;HANDLE file;DWORD length=0;
    if(!root_path(path,32768,L"Mods\\lllucky\\bootstrap.log"))return;
    file=CreateFileW(path,FILE_APPEND_DATA,FILE_SHARE_READ|FILE_SHARE_WRITE,NULL,OPEN_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL);
    if(file==INVALID_HANDLE_VALUE)return;
    while(text[length])++length;
    WriteFile(file,text,length,&written,NULL);CloseHandle(file);
}
static void early_environment(void) {
    WCHAR path[32768],buffer[8193],existing[2];DWORD bytes=0,i,n;HANDLE file;
    if(!is_game() || !root_path(path,32768,L"Mods\\lllucky\\bootstrap.ini"))return;
    file=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE,NULL,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,NULL);
    if(file==INVALID_HANDLE_VALUE)return;
    if(!ReadFile(file,buffer,16384,&bytes,NULL)){CloseHandle(file);return;}
    CloseHandle(file);
    if(bytes<2 || buffer[0]!=0xfeff)return;
    n=bytes/2;buffer[n]=0;i=1;
    while(i<n) {
        DWORD begin=i,end,eq;
        while(i<n && buffer[i]!=L'\r' && buffer[i]!=L'\n')++i;
        end=i;while(i<n && (buffer[i]==L'\r'||buffer[i]==L'\n'))++i;
        buffer[end]=0;eq=begin;
        while(eq<end && buffer[eq]!=L'=')++eq;
        if(eq==end)continue;
        buffer[eq]=0;
        if(same_ascii(buffer+begin,L"WGPU_BACKEND") || same_ascii(buffer+begin,L"WGPU_ADAPTER_NAME")
                || same_ascii(buffer+begin,L"WOW_ROGUE_SAVE")) {
            if(!GetEnvironmentVariableW(buffer+begin,existing,2))SetEnvironmentVariableW(buffer+begin,buffer+eq+1);
        }
    }
}
static DWORD WINAPI start_companion(void *unused) {
    WCHAR ini[32768],python[32768],backend[32768],command[65536];
    STARTUPINFOW si={0};PROCESS_INFORMATION pi={0};DWORD n;
    (void)unused;
    if(!root_path(ini,32768,L"Mods\\lllucky\\bootstrap.ini")
            || !root_path(backend,32768,L"Mods\\lllucky\\headless.py"))return 0;
    n=GetPrivateProfileStringW(L"lllucky",L"Pythonw",L"",python,32768,ini);
    if(!n || GetFileAttributesW(python)==INVALID_FILE_ATTRIBUTES || GetFileAttributesW(backend)==INVALID_FILE_ATTRIBUTES) {
        log_line("pythonw or companion path is unavailable\r\n");return 0;
    }
    command[0]=0;
    if(!append_text(command,65536,L"\"") || !append_text(command,65536,python)
            || !append_text(command,65536,L"\" -B \"") || !append_text(command,65536,backend)
            || !append_text(command,65536,L"\""))return 0;
    si.cb=sizeof(si);si.dwFlags=STARTF_USESHOWWINDOW;si.wShowWindow=SW_HIDE;
    if(CreateProcessW(python,command,NULL,NULL,FALSE,CREATE_NO_WINDOW,NULL,game_root,&si,&pi)) {
        CloseHandle(pi.hThread);CloseHandle(pi.hProcess);log_line("companion started\r\n");
    } else log_line("CreateProcessW failed\r\n");
    return 0;
}
static BOOL CALLBACK initialize(PINIT_ONCE init,void *parameter,void **context) {
    WCHAR path[32768];DWORD n;HANDLE thread;
    (void)init;(void)parameter;(void)context;
    n=GetSystemDirectoryW(path,32768);
    if(n && n<32750 && append_text(path,32768,L"\\dwmapi.dll"))real_dwm=LoadLibraryExW(path,NULL,LOAD_LIBRARY_SEARCH_SYSTEM32);
    if(is_game()) {
        thread=CreateThread(NULL,0,start_companion,NULL,0,NULL);
        if(thread)CloseHandle(thread);
    }
    return TRUE;
}
static FARPROC resolve(const char *name) {
    InitOnceExecuteOnce(&once,initialize,NULL,NULL);
    return real_dwm?GetProcAddress(real_dwm,name):NULL;
}

__declspec(dllexport) const char *llluckyBootstrapIdentity(void) { return identity; }
__declspec(dllexport) HRESULT WINAPI DwmEnableBlurBehindWindow(HWND hwnd,const void *blur) {
    typedef HRESULT (WINAPI *F)(HWND,const void *);F f=(F)resolve("DwmEnableBlurBehindWindow");return f?f(hwnd,blur):E_NOTIMPL;
}
__declspec(dllexport) HRESULT WINAPI DwmSetWindowAttribute(HWND hwnd,DWORD attribute,const void *value,DWORD size) {
    typedef HRESULT (WINAPI *F)(HWND,DWORD,const void *,DWORD);F f=(F)resolve("DwmSetWindowAttribute");return f?f(hwnd,attribute,value,size):E_NOTIMPL;
}
__declspec(dllexport) HRESULT WINAPI DwmGetWindowAttribute(HWND hwnd,DWORD attribute,void *value,DWORD size) {
    typedef HRESULT (WINAPI *F)(HWND,DWORD,void *,DWORD);F f=(F)resolve("DwmGetWindowAttribute");return f?f(hwnd,attribute,value,size):E_NOTIMPL;
}
__declspec(dllexport) HRESULT WINAPI DwmExtendFrameIntoClientArea(HWND hwnd,const void *margins) {
    typedef HRESULT (WINAPI *F)(HWND,const void *);F f=(F)resolve("DwmExtendFrameIntoClientArea");return f?f(hwnd,margins):E_NOTIMPL;
}
__declspec(dllexport) HRESULT WINAPI DwmIsCompositionEnabled(BOOL *enabled) {
    typedef HRESULT (WINAPI *F)(BOOL *);F f=(F)resolve("DwmIsCompositionEnabled");return f?f(enabled):E_NOTIMPL;
}
__declspec(dllexport) HRESULT WINAPI DwmGetColorizationColor(DWORD *color,BOOL *opaque) {
    typedef HRESULT (WINAPI *F)(DWORD *,BOOL *);F f=(F)resolve("DwmGetColorizationColor");return f?f(color,opaque):E_NOTIMPL;
}
__declspec(dllexport) HRESULT WINAPI DwmFlush(void) {
    typedef HRESULT (WINAPI *F)(void);F f=(F)resolve("DwmFlush");return f?f():E_NOTIMPL;
}
__declspec(dllexport) HRESULT WINAPI DwmEnableComposition(UINT action) {
    typedef HRESULT (WINAPI *F)(UINT);F f=(F)resolve("DwmEnableComposition");return f?f(action):E_NOTIMPL;
}
BOOL WINAPI DllMain(HINSTANCE module,DWORD reason,void *reserved) {
    DWORD n;
    (void)reserved;
    if(reason==DLL_PROCESS_ATTACH) {
        self_module=module;n=GetModuleFileNameW(self_module,game_root,32768);
        if(!n || n>=32768){game_root[0]=0;return TRUE;}
        while(n && game_root[n-1]!=L'\\' && game_root[n-1]!=L'/')--n;
        game_root[n]=0;early_environment();
    }
    return TRUE;
}
