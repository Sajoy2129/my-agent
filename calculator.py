"""A safe arithmetic calculator.

We never use eval(): it would run *any* Python code it is given.
Instead we parse the text into a syntax tree and only allow numbers
and math operators.
"""

import ast
import operator

MAX_EXPONENT = 100  # stops things like 9**9**9 from freezing the computer
MAX_EXPRESSION_LENGTH = 200  # characters; also limits how deeply it can nest
# Largest whole number allowed, in bits (about 3,000 digits). Without this,
# nesting like ((9**100)**100)**100 gets around MAX_EXPONENT.
MAX_RESULT_BITS = 10_000

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
    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise ValueError(
            f"Expression too long (max {MAX_EXPRESSION_LENGTH} characters)."
        )
    tree = ast.parse(expression, mode="eval")
    return _evaluate_node(tree.body)


def _evaluate_node(node):
    """Recursively evaluate one node of the syntax tree."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return _check_size(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in BINARY_OPERATORS:
        left = _evaluate_node(node.left)
        right = _evaluate_node(node.right)
        if isinstance(node.op, ast.Pow):
            _check_power(left, right)
        return _check_size(BINARY_OPERATORS[type(node.op)](left, right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in UNARY_OPERATORS:
        return UNARY_OPERATORS[type(node.op)](_evaluate_node(node.operand))
    raise ValueError(f"Unsupported expression: {ast.dump(node)}")


def _check_power(base, exponent):
    """Refuse a power BEFORE computing it if the answer would be too big.

    Checking afterwards is too late: the freeze happens during the
    calculation itself. A number with b bits raised to the power e has
    about b * e bits, so we can estimate the size cheaply.
    """
    if abs(exponent) > MAX_EXPONENT:
        raise ValueError(f"Exponent too large (max {MAX_EXPONENT}).")
    if isinstance(base, int) and exponent > 0:
        if base.bit_length() * exponent > MAX_RESULT_BITS:
            raise ValueError("Result too large to calculate.")


def _check_size(value):
    """Raise ValueError if a whole number is too big. Return it unchanged otherwise."""
    if isinstance(value, int) and value.bit_length() > MAX_RESULT_BITS:
        raise ValueError("Result too large to calculate.")
    return value
