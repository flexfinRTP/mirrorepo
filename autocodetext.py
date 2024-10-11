import os
import sys
import time
import argparse
import fnmatch
import gzip
import logging
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, scrolledtext
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from datetime import datetime
import difflib
import threading
import webbrowser

class CodeFileManager:
    def __init__(self):
        self.folder_path = ""
        self.output_file = ""
        self.extensions = []
        self.ignore_patterns = []
        self.compress = False
        self.custom_separator = "###"
        self.observer = None
        self.is_watching = False

    def read_file(self, file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                return file.read()
        except UnicodeDecodeError:
            try:
                with open(file_path, 'r', encoding='latin-1') as file:
                    return file.read()
            except:
                logging.error(f"Unable to read file: {file_path}")
                return f"[Unable to read file: {file_path}]"

    def write_output(self, content):
        if self.compress:
            with gzip.open(self.output_file + '.gz', 'wt', encoding='utf-8') as f:
                f.write(content)
        else:
            with open(self.output_file, 'w', encoding='utf-8') as f:
                f.write(content)

    def get_file_metadata(self, file_path):
        stat = os.stat(file_path)
        return f"Last modified: {datetime.fromtimestamp(stat.st_mtime)}, Size: {stat.st_size} bytes"

    def process_folder(self):
        content = ""
        total_files = sum(1 for _ in Path(self.folder_path).rglob('*') if _.is_file())
        processed_files = 0

        for root, _, files in os.walk(self.folder_path):
            for file in files:
                file_path = Path(root) / file
                relative_path = file_path.relative_to(self.folder_path)
                
                if any(fnmatch.fnmatch(str(relative_path), pattern) for pattern in self.ignore_patterns):
                    continue
                
                if self.extensions and not any(file.endswith(ext) for ext in self.extensions):
                    continue

                file_content = self.read_file(file_path)
                metadata = self.get_file_metadata(file_path)
                content += f"{self.custom_separator} File: {relative_path} {self.custom_separator}\n"
                content += f"# Location: {file_path}\n"
                content += f"# {metadata}\n\n"
                content += file_content
                content += f"\n\n{self.custom_separator} End of file {self.custom_separator}\n\n"

                processed_files += 1
                yield processed_files / total_files

        self.write_output(content)
        logging.info(f"Code files from {self.folder_path} have been consolidated into {self.output_file}")

    def update_output_file(self, changed_file):
        with open(self.output_file, 'r', encoding='utf-8') as f:
            content = f.read()

        relative_path = changed_file.relative_to(self.folder_path)
        new_content = self.read_file(changed_file)
        metadata = self.get_file_metadata(changed_file)
        
        file_header = f"{self.custom_separator} File: {relative_path} {self.custom_separator}\n"
        file_footer = f"\n\n{self.custom_separator} End of file {self.custom_separator}\n\n"
        
        start = content.find(file_header)
        if start != -1:
            end = content.find(file_footer, start) + len(file_footer)
            old_content = content[start:end]
            new_section = (f"{file_header}# Location: {changed_file}\n# {metadata}\n\n{new_content}{file_footer}")
            
            diff = list(difflib.unified_diff(old_content.splitlines(), new_section.splitlines(), lineterm=''))
            if diff:
                content = content[:start] + new_section + content[end:]
                self.write_output(content)
                logging.info(f"Updated {self.output_file} with changes from {relative_path}")
        else:
            new_section = (f"{file_header}# Location: {changed_file}\n# {metadata}\n\n{new_content}{file_footer}")
            content += new_section
            self.write_output(content)
            logging.info(f"Added new file {relative_path} to {self.output_file}")

    def start_watching(self):
        if not self.is_watching:
            self.is_watching = True
            self.observer = Observer()
            event_handler = CodeChangeHandler(self)
            self.observer.schedule(event_handler, self.folder_path, recursive=True)
            self.observer.start()
            logging.info("Started watching for changes.")

    def stop_watching(self):
        if self.is_watching:
            self.observer.stop()
            self.observer.join()
            self.is_watching = False
            logging.info("Stopped watching for changes.")

class CodeChangeHandler(FileSystemEventHandler):
    def __init__(self, manager):
        self.manager = manager

    def on_modified(self, event):
        if not event.is_directory:
            file_path = Path(event.src_path)
            relative_path = file_path.relative_to(self.manager.folder_path)

            if any(fnmatch.fnmatch(str(relative_path), pattern) for pattern in self.manager.ignore_patterns):
                return

            if self.manager.extensions and not any(file_path.name.endswith(ext) for ext in self.manager.extensions):
                return

            logging.info(f"File changed: {relative_path}")
            self.manager.update_output_file(file_path)

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Code File Manager")
        self.geometry("700x650")
        self.manager = CodeFileManager()
        self.is_dark_mode = False
        self.log_area = None  # Initialize log_area as None
        self.create_widgets()
        self.create_menu()
        self.bind_shortcuts()
        try:
            self.iconbitmap('path_to_icon.ico')  # Replace with actual path to your icon
        except tk.TclError:
            print("Icon file not found. Using default icon.")

    def create_widgets(self):
        self.style = ttk.Style()
        self.style.theme_use('clam')

        main_frame = ttk.Frame(self, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        main_frame.columnconfigure(1, weight=1)

        # Source Folder
        ttk.Label(main_frame, text="Source Folder:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.folder_path_entry = ttk.Entry(main_frame, width=50)
        self.folder_path_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), pady=5)
        ttk.Button(main_frame, text="Browse", command=self.browse_folder).grid(row=0, column=2, padx=5, pady=5)
        self.create_tooltip(self.folder_path_entry, "Select the folder containing your source code files")

        # Output File
        ttk.Label(main_frame, text="Output File:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.output_file_entry = ttk.Entry(main_frame, width=50)
        self.output_file_entry.grid(row=1, column=1, sticky=(tk.W, tk.E), pady=5)
        ttk.Button(main_frame, text="Browse", command=self.browse_output).grid(row=1, column=2, padx=5, pady=5)
        self.create_tooltip(self.output_file_entry, "Choose where to save the consolidated text file")

        # Extensions
        ttk.Label(main_frame, text="File Extensions:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.extensions_entry = ttk.Entry(main_frame, width=50)
        self.extensions_entry.grid(row=2, column=1, sticky=(tk.W, tk.E), pady=5)
        self.create_tooltip(self.extensions_entry, "Enter file extensions to include, separated by spaces (e.g., .py .js .html)")

        # Ignore Patterns
        ttk.Label(main_frame, text="Ignore Patterns:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.ignore_patterns_entry = ttk.Entry(main_frame, width=50)
        self.ignore_patterns_entry.grid(row=3, column=1, sticky=(tk.W, tk.E), pady=5)
        self.create_tooltip(self.ignore_patterns_entry, "Enter patterns to ignore, separated by spaces (e.g., *.log temp/*)")

        # Custom Separator
        ttk.Label(main_frame, text="Custom Separator:").grid(row=4, column=0, sticky=tk.W, pady=5)
        self.custom_separator_entry = ttk.Entry(main_frame, width=50)
        self.custom_separator_entry.insert(0, "###")
        self.custom_separator_entry.grid(row=4, column=1, sticky=(tk.W, tk.E), pady=5)
        self.create_tooltip(self.custom_separator_entry, "Enter a custom separator for file sections (default is ###)")

        # Compress Output
        self.compress_var = tk.BooleanVar()
        compress_checkbox = ttk.Checkbutton(main_frame, text="Compress Output", variable=self.compress_var)
        compress_checkbox.grid(row=5, column=0, columnspan=2, sticky=tk.W, pady=5)
        self.create_tooltip(compress_checkbox, "Check to compress the output file (will add .gz extension)")

        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=6, column=0, columnspan=3, pady=10)

        self.download_button = ttk.Button(button_frame, text="Download to Text", command=self.download_to_text)
        self.download_button.grid(row=0, column=0, padx=5)
        self.watch_button = ttk.Button(button_frame, text="Start Watching", command=self.toggle_watch)
        self.watch_button.grid(row=0, column=1, padx=5)

        # Log Area
        ttk.Label(main_frame, text="Activity Log:").grid(row=7, column=0, sticky=tk.W, pady=5)
        self.log_area = scrolledtext.ScrolledText(main_frame, wrap=tk.WORD, width=80, height=15)
        self.log_area.grid(row=8, column=0, columnspan=3, pady=5)
        self.log_area.config(state=tk.DISABLED)

        # Set up logging
        log_handler = TextHandler(self.log_area)
        logging.getLogger().addHandler(log_handler)
        logging.getLogger().setLevel(logging.INFO)

        # Status Bar
        self.status_var = tk.StringVar()
        self.status_var.set("Ready")
        self.status_bar = ttk.Label(self, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.grid(row=1, column=0, sticky=(tk.W, tk.E))

        self.configure_styles()  # Move this call here, after all widgets are created

    def create_menu(self):
        menubar = tk.Menu(self)
        self.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Exit", command=self.quit)
        menubar.add_cascade(label="File", menu=file_menu)

        edit_menu = tk.Menu(menubar, tearoff=0)
        edit_menu.add_command(label="Toggle Dark Mode", command=self.toggle_dark_mode)
        menubar.add_cascade(label="Edit", menu=edit_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="User Guide", command=self.show_user_guide)
        help_menu.add_command(label="About", command=self.show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

    def configure_styles(self):
        bg_color = "#f0f0f0" if not self.is_dark_mode else "#2c2c2c"
        fg_color = "black" if not self.is_dark_mode else "white"
        self.configure(bg=bg_color)
        self.style.configure('TFrame', background=bg_color)
        self.style.configure('TLabel', background=bg_color, foreground=fg_color)
        self.style.configure('TButton', background=bg_color, foreground=fg_color)
        self.style.configure('TCheckbutton', background=bg_color, foreground=fg_color)
        self.style.configure('TEntry', fieldbackground=bg_color, foreground=fg_color)
        self.log_area.config(bg=bg_color, fg=fg_color)
        self.status_bar.configure(background=bg_color, foreground=fg_color)

    def bind_shortcuts(self):
        self.bind("<Control-d>", lambda event: self.download_to_text())
        self.bind("<Control-w>", lambda event: self.toggle_watch())

    def toggle_watch(self):
        if not self.manager.is_watching:
            if not self.validate_inputs():
                return
            self.manager.folder_path = self.folder_path_entry.get()
            self.manager.output_file = self.output_file_entry.get()
            self.manager.extensions = [ext.strip() for ext in self.extensions_entry.get().split()]
            self.manager.ignore_patterns = [pat.strip() for pat in self.ignore_patterns_entry.get().split()]
            self.manager.compress = self.compress_var.get()
            self.manager.custom_separator = self.custom_separator_entry.get()

            self.manager.start_watching()
            self.watch_button.config(text="Stop Watching")
            self.status_var.set("Watching for changes...")
        else:
            self.manager.stop_watching()
            self.watch_button.config(text="Start Watching")
            self.status_var.set("Ready")

    def toggle_dark_mode(self):
        self.is_dark_mode = not self.is_dark_mode
        self.configure_styles()

    def create_tooltip(self, widget, text):
        tooltip = ToolTip(widget, text)

    def browse_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.folder_path_entry.delete(0, tk.END)
            self.folder_path_entry.insert(0, folder)

    def browse_output(self):
        file = filedialog.asksaveasfilename(defaultextension=".txt")
        if file:
            self.output_file_entry.delete(0, tk.END)
            self.output_file_entry.insert(0, file)

    def download_to_text(self):
        if not self.validate_inputs():
            return

        self.manager.folder_path = self.folder_path_entry.get()
        self.manager.output_file = self.output_file_entry.get()
        self.manager.extensions = [ext.strip() for ext in self.extensions_entry.get().split()]
        self.manager.ignore_patterns = [pat.strip() for pat in self.ignore_patterns_entry.get().split()]
        self.manager.compress = self.compress_var.get()
        self.manager.custom_separator = self.custom_separator_entry.get()

        try:
            self.status_var.set("Processing files...")
            self.download_button.config(state=tk.DISABLED)
            process_gen = self.manager.process_folder()
            self.show_progress(process_gen)
        except Exception as e:
            messagebox.showerror("Error", str(e))
            self.status_var.set("Error occurred")
        finally:
            self.download_button.config(state=tk.NORMAL)

    def validate_inputs(self):
        if not self.folder_path_entry.get():
            messagebox.showerror("Error", "Please specify the source folder.")
            return False
        if not self.output_file_entry.get():
            messagebox.showerror("Error", "Please specify the output file.")
            return False
        if not self.custom_separator_entry.get():
            messagebox.showerror("Error", "Please specify a custom separator.")
            return False
        return True

    def show_progress(self, generator):
        progress_window = tk.Toplevel(self)
        progress_window.title("Processing Files")
        progress_label = ttk.Label(progress_window, text="Consolidating files...")
        progress_label.pack(pady=5)
        progress_bar = ttk.Progressbar(progress_window, length=300, mode='determinate')
        progress_bar.pack(pady=10)

        def update_progress_bar():
            try:
                progress = next(generator)
                progress_bar['value'] = progress * 100
                self.status_var.set(f"Processing: {progress:.1%} complete")
                if progress < 1:
                    self.after(100, update_progress_bar)
                else:
                    progress_window.destroy()
                    messagebox.showinfo("Info", "Download to text completed.")
                    self.status_var.set("Ready")
            except StopIteration:
                progress_window.destroy()
                messagebox.showinfo("Info", "Download to text completed.")
                self.status_var.set("Ready")

        update_progress_bar()

    def show_user_guide(self):
        guide = tk.Toplevel(self)
        guide.title("User Guide")
        guide.geometry("600x400")
        text = scrolledtext.ScrolledText(guide, wrap=tk.WORD)
        text.pack(expand=True, fill='both')
        text.insert(tk.END, """
Code File Manager User Guide

1. Source Folder: Select the folder containing your source code files.
2. Output File: Choose where to save the consolidated text file.
3. File Extensions: Enter file extensions to include, separated by spaces (e.g., .py .js .html).
4. Ignore Patterns: Enter patterns to ignore, separated by spaces (e.g., *.log temp/*).
5. Custom Separator: Enter a custom separator for file sections (default is ###).
6. Compress Output: Check to compress the output file (will add .gz extension).
7. Download to Text: Click to consolidate files into a single text file.
8. Start/Stop Watching: Click to begin or end real-time file watching and updating.

Keyboard Shortcuts:
- Ctrl+D: Download to Text
- Ctrl+W: Toggle Watching

For more information, please visit our website or contact support.
        """)
        text.config(state=tk.DISABLED)

    def show_about(self):
        about_text = """
Code File Manager v5.0

Developed by: Your Name/Company
Copyright © 2023

This application helps you consolidate multiple code files into a single text file for easy review and analysis.

For more information, visit our website:
https://www.example.com/code-file-manager
        """
        messagebox.showinfo("About Code File Manager", about_text)

class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip = None
        self.widget.bind("<Enter>", self.show_tooltip)
        self.widget.bind("<Leave>", self.hide_tooltip)

    def show_tooltip(self, event=None):
        x, y, _, _ = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 25

        self.tooltip = tk.Toplevel(self.widget)
        self.tooltip.wm_overrideredirect(True)
        self.tooltip.wm_geometry(f"+{x}+{y}")

        label = tk.Label(self.tooltip, text=self.text, background="#ffffe0", relief="solid", borderwidth=1)
        label.pack()

    def hide_tooltip(self, event=None):
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip = None

class TextHandler(logging.Handler):
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget

    def emit(self, record):
        msg = self.format(record)
        self.text_widget.config(state=tk.NORMAL)
        self.text_widget.insert(tk.END, msg + '\n')
        self.text_widget.config(state=tk.DISABLED)
        self.text_widget.see(tk.END)

def main():
    app = App()
    app.mainloop()

if __name__ == "__main__":
    main()