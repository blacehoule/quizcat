#!/usr/bin/env python3

import os
import sys
import time
import questionary
from assets import open_eye_cat, wink_eye_cat, banner, preamble

os

PROGRAM_NAME = "QuizCat"

def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")

def display_banner():
    print(banner)

def display_begin_test():
    clear_screen()
    print(preamble)
    choice = questionary.select(
    "Selection: ",
    choices=[
        "Begin",
        "Return to Menu",
    ],
    ).ask()
    if choice == "Return to Menu":
        menu()
    if choice == "Begin":
        test()

def display_goodbye():
    clear_screen()
    print(open_eye_cat)
    time.sleep(1)
    clear_screen()
    print(wink_eye_cat)
    print(chr(7))
    time.sleep(.3)
    clear_screen()
    print(open_eye_cat)
    time.sleep(.3)

def test():
    
    clear_screen()


def begin_test():
    display_begin_test()


def quit_program():
    display_goodbye()
    clear_screen()
    sys.exit(0)

def menu():
    clear_screen()
    display_banner()
    
    choice = questionary.select(
        "Please choose an option:",
        choices=[
            "Begin Test",
            "Quit",
        ],
    ).ask()

    if choice is None:
        quit_program()

    if choice == "Begin Test":
        begin_test()

    if choice == "Quit":
        quit_program()

def main():
    menu()


if __name__ == "__main__":
    main()