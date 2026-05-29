from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Placeholder, Markdown, ListView, ListItem, Label, ProgressBar, Button, Switch
from textual.containers import Horizontal, Vertical, Center, HorizontalGroup
from textual.screen import Screen
from textual.timer import Timer

from example_question import EXAMPLE_QUESTION, EXAMPLE_ANSWERS
choices = list([f"{k}. {v}" for k, v in EXAMPLE_ANSWERS.items()])
# choices = list([ListItem(Label(f"{k}. {v}")) for k, v in EXAMPLE_ANSWERS.items()])
# print(choices)

class ControlPanel(HorizontalGroup):

    def compose(self) -> ComposeResult:
        yield HorizontalGroup(Button("Pause", id="pause", variant="warning"),
                               Button("Abort", id="abort", variant="error"),
                               Button("Submit", id="submit", variant="success"))

class QAPanel(HorizontalGroup):        

    def compose(self) -> ComposeResult:
        yield HorizontalGroup(Markdown(EXAMPLE_QUESTION, id="Q"),
                              ListView(*list([ListItem(Label(x)) for x in choices]), id="A"))
                              

class QuizScreen(Screen):
    """ Quiz Screen """
    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()
        with Vertical():
            yield ProgressBar()
            yield ProgressBar()
            # yield Markdown(EXAMPLE_QUESTION)
            # yield ListView(*list([ListItem(Label(x)) for x in choices]))
            yield QAPanel()
            yield ControlPanel(id="Control_Panel")

class Quizcat(App):
    """ Main App """
    BINDINGS = [("d", "toggle_dark", "Toggle dark mode")]
    TITLE = "QuizCat"
    SUB_TITLE = "Cognitive Quizzes in the Command Line"
    CSS_PATH = "quizcat.tcss"

    def on_ready(self) -> None:
        self.push_screen(QuizScreen())

    def action_toggle_dark(self) -> None:
        """An action to toggle dark mode."""
        self.theme = (
            "textual-dark" if self.theme == "textual-light" else "textual-light"
        )

if __name__=='__main__':
    app = Quizcat()
    app.run()
