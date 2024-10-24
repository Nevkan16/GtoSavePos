import tkinter as tk
from tkinter import scrolledtext
import win32gui
import win32con
import win32process
import json
import psutil
import time
import threading
import configparser
from tkinter import Tk, PhotoImage
from PIL import Image, ImageTk

# Path to the file with the saved gto position
window_position_file = 'gto_position.json'

# Path to the file with the saved win position
CONFIG_FILE = 'win_position.ini'

# Global variables for storing the current window position and PID of the process
current_position = None
hwnd = None
current_pid = None

# Flags for tracking the position loading and changes
loaded_position = False
last_saved_position = None
minimized_windows = {}
MAX_LOG_ROWS = 4


def save_window_position(hwnd):
    if hwnd and win32gui.IsWindow(hwnd):
        rect = win32gui.GetWindowRect(hwnd)
        if rect[0] == -32000 and rect[1] == -32000:
            if hwnd not in minimized_windows:
                add_log("Window is minimized. Skipping save position.")
                minimized_windows[hwnd] = True
            return None
        position = {
            'x': rect[0],
            'y': rect[1],
            'width': rect[2] - rect[0],
            'height': rect[3] - rect[1]
        }
        return position
    else:
        add_log("Invalid window handle. Cannot save window position.")
        return None


def set_window_position(hwnd, position):
    if hwnd and win32gui.IsWindow(hwnd):
        try:
            win32gui.SetWindowPos(
                hwnd,
                win32con.HWND_TOP,
                position['x'],
                position['y'],
                position['width'],
                position['height'],
                win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE | win32con.SWP_SHOWWINDOW
            )
            add_log(f"Window position set to: {position}")
        except win32gui.error as e:
            add_log(f"Failed to set window position: {e}")
    else:
        add_log("Invalid window handle. Cannot set window position.")


def find_window_by_pid(pid):
    def callback(hwnd, extra):
        if win32gui.IsWindowVisible(hwnd):
            found_pid = win32process.GetWindowThreadProcessId(hwnd)[1]
            if found_pid == pid:
                extra.append(hwnd)

    hwnd_list = []
    win32gui.EnumWindows(callback, hwnd_list)
    return hwnd_list[0] if hwnd_list else None


def save_position_to_file(position):
    if position:
        with open(window_position_file, 'w') as file:
            json.dump(position, file)
        add_log(f"Window position saved to file: {position}")
    else:
        add_log("No position to save.")


def load_position_from_file():
    try:
        with open(window_position_file, 'r') as file:
            position = json.load(file)
            add_log(f"Loaded window position from file: {position}")
            return position
    except FileNotFoundError:
        add_log("Window position file not found.")
        return None


def apply_position_from_file(hwnd):
    saved_position = load_position_from_file()
    if saved_position:
        set_window_position(hwnd, saved_position)
        return True
    return False


def monitor_gto_process(log_text, exit_event):
    global current_position, hwnd, current_pid, loaded_position, last_saved_position
    while not exit_event.is_set():
        gto_pid = None
        for proc in psutil.process_iter(['pid', 'name']):
            if proc.info['name'].lower() == "gto.exe":
                gto_pid = proc.info['pid']
                break

        if gto_pid is None:
            if current_pid is not None:
                add_log("GTO.exe process ended.")
                current_pid = None
                hwnd = None
                loaded_position = False
            time.sleep(2)
            continue

        if gto_pid != current_pid:
            current_pid = gto_pid
            hwnd = find_window_by_pid(current_pid)
            loaded_position = False
            add_log("New GTO.exe process started.")

        if not hwnd:
            hwnd = find_window_by_pid(current_pid)
            if not hwnd:
                time.sleep(1)
                continue

        if not loaded_position and hwnd:
            time.sleep(1)
            if apply_position_from_file(hwnd):
                add_log("Loaded window position from file and applied.")
            loaded_position = True

        if hwnd and win32gui.IsWindow(hwnd):
            current_position = save_window_position(hwnd)
            if current_position and current_position != last_saved_position:
                save_position_to_file(current_position)
                add_log(f"x - {current_position['x']},\n"
                        f"y - {current_position['y']}.\n"
                        f"w - {current_position['width']},\n"
                        f"h - {current_position['height']}.")
                last_saved_position = current_position

        else:
            add_log("Invalid window handle. Cannot save window position.")

        time.sleep(2)

def save_win_position(root):
    """Save the current position of the window to a config file."""
    config = configparser.ConfigParser()
    config['WindowPosition'] = {
        'x': root.winfo_x(),
        'y': root.winfo_y()
    }
    with open(CONFIG_FILE, 'w') as configfile:
        config.write(configfile)

def load_win_position():
    """Load the window position from the config file."""
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    if 'WindowPosition' in config:
        x = config.getint('WindowPosition', 'x', fallback=100)
        y = config.getint('WindowPosition', 'y', fallback=100)
        return x, y
    return 280, 120


def add_log(message):
    log_text.config(state=tk.NORMAL)  # Разрешаем редактирование текста
    log_text.delete(1.0, tk.END)  # Очищаем весь текст
    formatted_message = message.replace(", ", ",")  # Заменяем ", " на "," и добавляем новую строку
    log_text.insert(tk.END, formatted_message)  # Добавляем новое сообщение и переходим на новую строку
    log_text.config(state=tk.DISABLED)  # Запрещаем редактирование текста
    log_text.yview(tk.END)  # Прокручиваем до конца


def copy_selection(event=None):
    root.clipboard_clear()
    text = log_text.selection_get()
    root.clipboard_append(text)


def show_context_menu(event):
    context_menu.post(event.x_root, event.y_root)


def main():
    global current_pid, hwnd, root, log_text, context_menu, exit_event


    root = tk.Tk()
    root.title("GTO Save Position")

    # Попытка загрузки иконки
    try:
        img = Image.open("pos.ico")
        icon = ImageTk.PhotoImage(img)
        root.iconphoto(True, icon)  # Устанавливаем иконку
    except Exception as e:
        print(f"Иконка не найдена или произошла ошибка: {e}")
        # Можно установить альтернативную иконку или просто продолжить работу

    x, y = load_win_position()

    root.geometry(f"280x120+{x}+{y}")
    root.resizable(False, False)

    log_text = scrolledtext.ScrolledText(root, height=MAX_LOG_ROWS, width=50)
    log_text.pack()

    # Context
    # Context menu for copying text
    context_menu = tk.Menu(root, tearoff=0)
    context_menu.add_command(label="Copy", command=copy_selection)

    log_text.bind("<Button-3>", show_context_menu)  # Right-click to show context menu
    log_text.bind("<Control-c>", copy_selection)  # Ctrl+C to copy selected text

    exit_event = threading.Event()  # Создаем событие для завершения потока мониторинга
    monitor_thread = None

    def start_monitor():
        nonlocal monitor_thread
        exit_event.clear()
        start_button.config(state="disabled")
        finish_button.config(state="normal")
        monitor_thread = threading.Thread(target=monitor_gto_process, args=(log_text, exit_event))
        monitor_thread.daemon = True
        monitor_thread.start()
        add_log("Monitoring started.")

    def finish_monitor():
        nonlocal monitor_thread
        exit_event.set()
        if monitor_thread is not None:
            monitor_thread.join()
        start_button.config(state="normal")
        finish_button.config(state="disabled")
        add_log("Monitoring stopped.")

    def on_closing():
        finish_monitor()
        save_win_position(root)
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)

    start_button = tk.Button(root, text="Start", command=start_monitor)
    start_button.pack(side=tk.LEFT, padx=5, pady=5)

    finish_button = tk.Button(root, text="Finish", command=finish_monitor, state="disabled")
    finish_button.pack(side=tk.LEFT, padx=5, pady=5)

    gto_pid = None
    for proc in psutil.process_iter(['pid', 'name']):
        if proc.info['name'].lower() == "gto.exe":
            gto_pid = proc.info['pid']
            break
    if gto_pid is not None:
        hwnd = find_window_by_pid(gto_pid)
        if hwnd:
            apply_position_from_file(hwnd)
            loaded_position = True
            current_pid = gto_pid
            add_log("Initial GTO.exe process found and window position loaded.")

    # Automatically start the monitor
    start_monitor()

    root.mainloop()


if __name__ == "__main__":
    main()
