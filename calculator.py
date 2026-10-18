"""A safe arithmetic calculator.

We never use eval(): it would run *any* Python code it is given.
Instead we parse the text into a syntax tree and only allow numbers
and math operators.
"""

import ast
import operator

MAX_EXPONENT = 100  # stops things like 9**9**9 from freezing the computer

# Maps each allowed syntax-tree node type to the Python function that runs it.
BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
UNARY_OPERATORS = {ast.USub: operator.neg, ast.UAdd: operator.pos}


def safe_calculate(expression):
    """Evaluate arithmetic like '(3 + 4) * 2'.

    Raises ValueError for anything that isn't math, SyntaxError for
    text that isn't valid, and ZeroDivisionError for division by zero.
    """
    tree = ast.parse(expression, mode="eval")
    return _evaluate_node(tree.body)


def _evaluate_node(node):
    """Recursively evaluate one node of the syntax tree."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in BINARY_OPERATORS:
        left = _evaluate_node(node.left)
        right = _evaluate_node(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > MAX_EXPONENT:
            raise ValueError(f"Exponent too large (max {MAX_EXPONENT}).")
        return BINARY_OPERATORS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in UNARY_OPERATORS:
        return UNARY_OPERATORS[type(node.op)](_evaluate_node(node.operand))
    raise ValueError(f"Unsupported expression: {ast.dump(node)}")
