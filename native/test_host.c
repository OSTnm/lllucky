#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
__declspec(dllimport) HRESULT WINAPI DwmIsCompositionEnabled(BOOL *enabled);
int wmain(void) {
    WCHAR value[32768],path[32768];DWORD n;BOOL enabled=FALSE;int i;
    n=GetEnvironmentVariableW(L"WGPU_BACKEND",value,32768);
    if(!n || lstrcmpW(value,L"lllucky-test")!=0)return 11;
    n=GetEnvironmentVariableW(L"WOW_ROGUE_SAVE",value,32768);
    if(!n || lstrcmpW(value,L"X:\\lllucky-test\\characters.txt")!=0)return 12;
    DwmIsCompositionEnabled(&enabled);
    n=GetModuleFileNameW(NULL,path,32768);
    while(n && path[n-1]!=L'\\')--n;
    path[n]=0;lstrcatW(path,L"Mods\\lllucky\\started.flag");
    for(i=0;i<100;++i){if(GetFileAttributesW(path)!=INVALID_FILE_ATTRIBUTES){puts("Native EXE autostart integration: OK");return 0;}Sleep(100);}
    return 13;
}
