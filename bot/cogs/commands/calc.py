# ╔══════════════════════════════════════════════════════════════════╗
# ║                                                                  ║
# ║   ░█▀▀░█▀█░█▀▄░█▀▀░█░█   ░█▀▄░█▀▀░█░█░█▀▀                     ║
# ║   ░█░░░█░█░█░█░█▀▀░▄▀▄   ░█░█░█▀▀░▀▄▀░▀▀█                     ║
# ║   ░▀▀▀░▀▀▀░▀▀░░▀▀▀░▀░▀   ░▀▀░░▀▀▀░░▀░░▀▀▀                     ║
# ║                                                                  ║
# ║            © 2026 UniversityBot Devs — All Rights Reserved              ║
# ║                                                                  ║
# ║   discord  ──  https://discord.gg/MG3rYnUZJV                      ║
# ║   youtube  ──  https://youtube.com/@UniversityBotDevs                   ║
# ║   github   ──  https://github.com/UniversityBot                        ║
# ║                                                                  ║
# ╚══════════════════════════════════════════════════════════════════╝

from discord.ext import commands
from discord.ui import View, Button, button, LayoutView, ActionRow, Container, TextDisplay, Separator
import discord

import ast
import operator
from utils.emoji import DELETE


# Safe arithmetic evaluation.
#
# Using eval() here would execute arbitrary Python. Even though the calculator
# only offers digit and operator buttons today, eval() on a user-controlled
# string is a remote code execution primitive waiting to happen. Instead the
# expression is parsed into an AST and only a small whitelist of arithmetic
# nodes is evaluated.
_ALLOWED_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.FloorDiv: operator.floordiv,
}

_ALLOWED_UNARY_OPERATORS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

# Guards against expressions like 9**9**9 that would hang the event loop.
_MAX_EXPONENT = 128
_MAX_EXPRESSION_LENGTH = 100


class CalculationError(Exception):
    """Raised when an expression is invalid or not allowed."""


def _evaluate_node(node):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise CalculationError("Only numbers are allowed.")
        return node.value

    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_BINARY_OPERATORS:
            raise CalculationError("Operator not allowed.")
        left = _evaluate_node(node.left)
        right = _evaluate_node(node.right)
        if op_type is ast.Pow and (abs(right) > _MAX_EXPONENT or abs(left) > _MAX_EXPONENT):
            raise CalculationError("Exponent too large.")
        return _ALLOWED_BINARY_OPERATORS[op_type](left, right)

    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_UNARY_OPERATORS:
            raise CalculationError("Operator not allowed.")
        return _ALLOWED_UNARY_OPERATORS[op_type](_evaluate_node(node.operand))

    raise CalculationError("Expression not allowed.")


def safe_eval(expression: str):
    """Evaluate a purely arithmetic expression without using eval()."""
    expression = (expression or "").strip()
    if not expression:
        raise CalculationError("Empty expression.")
    if len(expression) > _MAX_EXPRESSION_LENGTH:
        raise CalculationError("Expression too long.")

    try:
        parsed = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise CalculationError("Invalid expression.") from exc

    result = _evaluate_node(parsed.body)

    if isinstance(result, float):
        if result != result or result in (float("inf"), float("-inf")):
            raise CalculationError("Result is not a finite number.")
        if result.is_integer():
            return int(result)
        return round(result, 10)
    return result


class _CalcRow(ActionRow):
    """
    One row of calculator keys.

    A LayoutView ignores @button decorators -- verified: the class comes
    out with zero children -- and it has no `row=` either, because rows
    are real objects in V2 rather than a number on each button. So each
    row is its own ActionRow, and the keys keep their decorators.
    """

    def __init__(self, view: "CalculatorView"):
        super().__init__()
        self._view = view


class _Row0(_CalcRow):
    @button(label="1", style=discord.ButtonStyle.grey)
    async def one(self, interaction: discord.Interaction, item: Button):
        await self._view.update_value(interaction, "1")

    @button(label="2", style=discord.ButtonStyle.grey)
    async def two(self, interaction: discord.Interaction, item: Button):
        await self._view.update_value(interaction, "2")

    @button(label="3", style=discord.ButtonStyle.grey)
    async def three(self, interaction: discord.Interaction, item: Button):
        await self._view.update_value(interaction, "3")


class _Row1(_CalcRow):
    @button(label="4", style=discord.ButtonStyle.grey)
    async def four(self, interaction: discord.Interaction, item: Button):
        await self._view.update_value(interaction, "4")

    @button(label="5", style=discord.ButtonStyle.grey)
    async def five(self, interaction: discord.Interaction, item: Button):
        await self._view.update_value(interaction, "5")

    @button(label="6", style=discord.ButtonStyle.grey)
    async def six(self, interaction: discord.Interaction, item: Button):
        await self._view.update_value(interaction, "6")


class _Row2(_CalcRow):
    @button(label="7", style=discord.ButtonStyle.grey)
    async def seven(self, interaction: discord.Interaction, item: Button):
        await self._view.update_value(interaction, "7")

    @button(label="8", style=discord.ButtonStyle.grey)
    async def eight(self, interaction: discord.Interaction, item: Button):
        await self._view.update_value(interaction, "8")

    @button(label="9", style=discord.ButtonStyle.grey)
    async def nine(self, interaction: discord.Interaction, item: Button):
        await self._view.update_value(interaction, "9")


class _Row3(_CalcRow):
    @button(label="0", style=discord.ButtonStyle.grey)
    async def zero(self, interaction: discord.Interaction, item: Button):
        await self._view.update_value(interaction, "0")

    @button(label="+", style=discord.ButtonStyle.blurple)
    async def add(self, interaction: discord.Interaction, item: Button):
        await self._view.update_value(interaction, "+")

    @button(label="-", style=discord.ButtonStyle.blurple)
    async def subtract(self, interaction: discord.Interaction, item: Button):
        await self._view.update_value(interaction, "-")

    @button(label="*", style=discord.ButtonStyle.blurple)
    async def multiply(self, interaction: discord.Interaction, item: Button):
        await self._view.update_value(interaction, "*")

    @button(label="/", style=discord.ButtonStyle.blurple)
    async def divide(self, interaction: discord.Interaction, item: Button):
        await self._view.update_value(interaction, "/")


class _Row4(_CalcRow):
    @button(label="=", style=discord.ButtonStyle.green)
    async def equals(self, interaction: discord.Interaction, item: Button):
        if interaction.user != self._view.author:
            return await interaction.response.send_message(
                "This is not your embed.", ephemeral=True
            )
        try:
            expression = self._view.value.strip().replace("\n", "")
            result = str(safe_eval(expression))
            await self._view.update_embed(interaction, result)
            # Store the result for possible further calculations
            self._view.value = result
        except (CalculationError, ZeroDivisionError, ArithmeticError, ValueError):
            await self._view.update_embed(interaction, "Error")

    @button(label="Clear", emoji=DELETE, style=discord.ButtonStyle.red)
    async def clear(self, interaction: discord.Interaction, item: Button):
        await self._view.update_value(interaction, "Clear")


class CalculatorView(LayoutView):
    """
    The calculator, as a Components V2 panel.

    The display is a TextDisplay inside the container rather than the
    message content, so the keys sit in the same card as the number they
    are typing -- which is the whole point of the conversion.

    It rebuilds itself on every keypress instead of handing its children
    to a helper: from_view() *moves* the components out of the view it is
    given, so a view that is sent again later would arrive with no
    buttons at all. The calculator is edited on every single press, so
    that would have left it keyless after the first one.
    """

    def __init__(self, author: discord.Member):
        super().__init__(timeout=180)
        self.author = author
        self.value = ""
        self.message = None
        self._render("")

    def _render(self, result: str) -> None:
        self.clear_items()
        box = Container(accent_color=0x5865F2)
        box.add_item(TextDisplay(
            f"### Calculator\n-# {self.author.display_name}\n"
            f"```\n{result or ' '}\n```"
        ))
        box.add_item(Separator(visible=True))
        for row in (_Row0, _Row1, _Row2, _Row3, _Row4):
            box.add_item(row(self))
        self.add_item(box)

    async def update_value(self, interaction: discord.Interaction, value: str):
        # Check if the person interacting is the author of the embed
        if interaction.user != self.author:
            return await interaction.response.send_message(
                "This content does not appear to be part of your embedded materials.",
                ephemeral=True,
            )
        # Append the value or clear if "Clear"
        if value == "Clear":
            self.value = ""
        else:
            self.value += value
        # Update the panel with the new value
        await self.update_embed(interaction, self.value)

    async def update_embed(self, interaction: discord.Interaction, result: str):
        self._render(result)
        await interaction.response.edit_message(view=self)
        self.message = interaction.message


class calculator(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='calculator', help='Starts a calculator session', aliases=['calc', 'calculate', 'math'])
    async def calculator(self, ctx):
        """Starts a new calculator session."""
        # Ensure we pass the author to the view so it knows who triggered it
        view = CalculatorView(author=ctx.author)
        # We store the message so we know what to edit and update later
        # No content=: the display lives inside the panel now, so
        # sending it alongside would print the number twice.
        view.message = await ctx.send(view=view)

# Add the cog to the bot
def setup(bot):
    bot.add_cog(calculator(bot))

