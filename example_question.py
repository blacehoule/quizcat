EXAMPLE_QUESTION = """\
## Question X

> Choose the word or words that, when inserted in the sentence to replace the blank or blanks, best fits the meaning of the sentence.

The debate quickly became _____, with neither side willing to compromise or entertain the other’s viewpoint.
"""

EXAMPLE_ANSWERS = { 
    'A': 'harmonious',
    'B': 'civil',
    'C': 'intractable',
    'D': 'constructive',
    'E': 'exotic'
    }

EXAMPLE_MARKDOWN = """\
## Markdown

- Typography *emphasis*, **strong**, `inline code` etc.    
- Headers    
- Lists    
- Syntax highlighted code blocks
- Tables and more

## Quotes

> I must not fear.
> > Fear is the mind-killer.
> > Fear is the little-death that brings total obliteration.
> > I will face my fear.
> > > I will permit it to pass over me and through me.
> > > And when it has gone past, I will turn the inner eye to see its path.
> > > Where the fear has gone there will be nothing. Only I will remain.

## Tables

| Name            | Type   | Default | Description                        |
| --------------- | ------ | ------- | ---------------------------------- |
| `show_header`   | `bool` | `True`  | Show the table header              |
| `fixed_rows`    | `int`  | `0`     | Number of fixed rows               |
| `fixed_columns` | `int`  | `0`     | Number of fixed columns            |

## Code blocks

```python
def loop_last(values: Iterable[T]) -> Iterable[Tuple[bool, T]]:
    \"\"\"Iterate and generate a tuple with a flag for last value.\"\"\"
    iter_values = iter(values)
    try:
        previous_value = next(iter_values)
    except StopIteration:
        return
    for value in iter_values:
        yield False, previous_value
        previous_value = value
    yield True, previous_value
```


"""