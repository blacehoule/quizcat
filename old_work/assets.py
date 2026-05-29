
wink_eye_cat = r"""


     Thank You From
         /\_/\
        ( o.- )
        QuizCat

"""
open_eye_cat = r"""


     Thank You From
         /\_/\
        ( o.o )
        QuizCat


"""

banner = r"""
   ____        _        ____      _   
  / __ \      (_)      / ___|__ _| |_ 
 | |  | |_   _ _ ____ | |   / _` | __|
 | |__| | |_| | |_  / | |__| (_| | |_ 
  \___\_\\__,_|_/___/  \____\__,_|\__|

        Multiple Choice Practice Tests
"""

preamble = r"""

        Multiple Choice Practice Test

                     /\_/\
                    ( o.o )
                    QuizCat

This is a timed multiple choice test designed to
mimic CCAT test conditions. You will have 12 min
to answer 40 questions. Select 'Begin' to start
     your timed test, or 'Return to Menu'
"""


q_card = f"""

{{0}}

{{1}}
"""

print(q_card.format("Hello,", "World!"))

import pandas as pd

def build_test():
        questions = pd.read_csv("questions_clean.csv", index_col=0)
        eqrfa

import pandas as pd
questions = pd.read_csv("questions_clean.csv", index_col=0)
print(questions.head())

questions.groupby('subcategory').sample()

def help():
        