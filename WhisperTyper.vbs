Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "D:\Coding\whisper-typer"
WshShell.Run "pythonw whisper_typer.py", 0, False
