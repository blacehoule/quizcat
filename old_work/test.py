import pandas as pd
import numpy as np


def generate_test():
    df = pd.read_csv("questions_clean.csv", index_col=0)
    df = df.astype(object).replace({np.nan: None})

    df_list = []
    df_list.append(df[df['subcategory'] == 'Basic Arithmetic Word Problems'].sample(n=14))
    df_list.append(df[df['subcategory'] == 'Sentence Completion'].sample(n=8))
    df_list.append(df[df['subcategory'] == 'Analogies'].sample(n=5))
    df_list.append(df[df['subcategory'] == 'Logic Statements'].sample(n=4))
    df_list.append(df[df['subcategory'] == 'Exact Match Count'].sample(n=3))
    df_list.append(df[df['subcategory'] == 'Opposites'].sample(n=2))
    df_list.append(df[df['subcategory'] == 'Letter Series'].sample(n=1))
    df_list.append(df[df['subcategory'] == 'Number Series'].sample(n=1))
    df_list.append(df[df['subcategory'] == 'Number Comparison'].sample(n=1))
    df_list.append(df[df['subcategory'] == 'Ordering and Arrangement Logic'].sample(n=1))

    return pd.concat(df_list).sample(frac=1).reset_index(drop=True)

q_card = f"""

{{0}}

{{1}}
"""

def Test(questions):

    for idx, question in questions.iterrows():
        table = ""
        if question.stimulus:
            print(question.stimulus)
        #     table = "\n|" + "-"*41 + "|" + "-"*41 + "|\n"
        #     pairs = question.stimulus['pairs']
        #     for left, right in pairs:
        #         table += f"| {left:<40}| {right:<40}|\n"
        #         table += "|" + "-"*41 + "|" + "-"*41 + "|\n"
        # print(q_card.format(question.prompt, table))
        # choice = questionary.select(
        #     "Please choose an option:",
        #     choices=[': '.join(x) for x in question.choices.items()],
        # ).ask()



# df_final = generate_test()

# Test(df_final)

# q0 = df_final.iloc[0]

# q_card = f"""

# {{0}}

# {{1}}
# """

# import ast
# import questionary

# print(q_card.format(q0.prompt, ''))
# choices = ast.literal_eval(q0.choices)
# choice = questionary.select(
#     "Please choose an option:",
#     choices=[': '.join(x) for x in choices.items()],
# ).ask()

def main():
    df_final = generate_test()
    # Test(df_final)
    print(df_final.info())
    print(df_final.head())



if __name__ == "__main__":
    main()