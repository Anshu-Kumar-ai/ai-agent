#!/usr/bin/env python3
"""
Simple Desktop Test Fixture - Phase 6
A small tkinter application with predictable controls for desktop automation testing.
"""
import tkinter as tk
from tkinter import ttk
import threading
import time


class DesktopTestFixture:
    """Simple test application with known window title and controls."""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Desktop Test Fixture - Phase 6")
        self.root.geometry("600x400")
        self.root.resizable(True, True)
        
        # Counter for click testing
        self.click_count = 0
        
        # Create UI elements
        self._create_widgets()
        
        # Track window state
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        
    def _create_widgets(self):
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title label
        title_label = ttk.Label(main_frame, text="Desktop Test Fixture", font=("Arial", 16, "bold"))
        title_label.pack(pady=(0, 20))
        
        # Counter section
        counter_frame = ttk.LabelFrame(main_frame, text="Click Counter", padding="10")
        counter_frame.pack(fill=tk.X, pady=10)
        
        self.counter_label = ttk.Label(counter_frame, text="Count: 0", font=("Arial", 14))
        self.counter_label.pack(pady=5)
        
        self.increment_btn = ttk.Button(counter_frame, text="Increment", command=self._increment_counter)
        self.increment_btn.pack(pady=5)
        
        # Text input section
        input_frame = ttk.LabelFrame(main_frame, text="Text Input", padding="10")
        input_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(input_frame, text="Enter text:").pack(anchor=tk.W)
        self.text_entry = ttk.Entry(input_frame, width=50)
        self.text_entry.pack(fill=tk.X, pady=5)
        
        self.clear_btn = ttk.Button(input_frame, text="Clear", command=self._clear_text)
        self.clear_btn.pack(anchor=tk.W, pady=5)
        
        # Checkbox section
        check_frame = ttk.LabelFrame(main_frame, text="Checkboxes", padding="10")
        check_frame.pack(fill=tk.X, pady=10)
        
        self.check_var1 = tk.BooleanVar()
        self.check_var2 = tk.BooleanVar()
        self.check_var3 = tk.BooleanVar()
        
        ttk.Checkbutton(check_frame, text="Option 1", variable=self.check_var1).pack(anchor=tk.W)
        ttk.Checkbutton(check_frame, text="Option 2", variable=self.check_var2).pack(anchor=tk.W)
        ttk.Checkbutton(check_frame, text="Option 3", variable=self.check_var3).pack(anchor=tk.W)
        
        # Read checkboxes button
        ttk.Button(check_frame, text="Read Checkboxes", command=self._read_checkboxes).pack(pady=5)
        
        # Result display
        result_frame = ttk.LabelFrame(main_frame, text="Result Display", padding="10")
        result_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        self.result_text = tk.Text(result_frame, height=6, width=60)
        self.result_text.pack(fill=tk.BOTH, expand=True)
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(result_frame, orient=tk.VERTICAL, command=self.result_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.result_text.config(yscrollcommand=scrollbar.set)
        
        # Buttons at bottom
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(btn_frame, text="Send Keys Test (ENTER)", command=self._send_enter).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Tab Test", command=self._tab_test).pack(side=tk.LEFT, padx=5)
        
    def _increment_counter(self):
        self.click_count += 1
        self.counter_label.config(text=f"Count: {self.click_count}")
        self._log(f"Button clicked. Count: {self.click_count}")
        
    def _clear_text(self):
        self.text_entry.delete(0, tk.END)
        self._log("Text cleared")
        
    def _read_checkboxes(self):
        values = []
        if self.check_var1.get():
            values.append("Option 1")
        if self.check_var2.get():
            values.append("Option 2")
        if self.check_var3.get():
            values.append("Option 3")
        result = ", ".join(values) if values else "None selected"
        self._log(f"Checkboxes: {result}")
        
    def _send_enter(self):
        self._log("ENTER key simulated")
        
    def _tab_test(self):
        self.text_entry.focus_set()
        self._log("Tab focus set to text entry")
        
    def _log(self, message):
        timestamp = time.strftime("%H:%M:%S")
        self.result_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.result_text.see(tk.END)
        
    def _on_close(self):
        self.root.quit()
        self.root.destroy()
        
    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = DesktopTestFixture()
    app.run()