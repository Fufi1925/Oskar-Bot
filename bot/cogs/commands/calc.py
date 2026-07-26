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
from discord.ui import View, Button, button
import discord

import ast
import operator


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


class CalculatorView(View):
    def __init__(self, author: discord.Member):
        super().__init__()
        self.author = author
        self.value = ""
        self.message = None

    # Button interactions 
    @button(label="1", style=discord.ButtonStyle.grey, row=0)
    async def one(self, interaction: discord.Interaction, button: Button):
        await self.update_value(interaction, "1")

    @button(label="2", style=discord.ButtonStyle.grey, row=0)
    async def two(self, interaction: discord.Interaction, button: Button):
        await self.update_value(interaction, "2")

    @button(label="3", style=discord.ButtonStyle.grey, row=0)
    async def three(self, interaction: discord.Interaction, button: Button):
        await self.update_value(interaction, "3")

    @button(label="4", style=discord.ButtonStyle.grey, row=1)
    async def four(self, interaction: discord.Interaction, button: Button):
        await self.update_value(interaction, "4")

    @button(label="5", style=discord.ButtonStyle.grey, row=1)
    async def five(self, interaction: discord.Interaction, button: Button):
        await self.update_value(interaction, "5")

    @button(label="6", style=discord.ButtonStyle.grey, row=1)
    async def six(self, interaction: discord.Interaction, button: Button):
        await self.update_value(interaction, "6")

    @button(label="7", style=discord.ButtonStyle.grey, row=2)
    async def seven(self, interaction: discord.Interaction, button: Button):
        await self.update_value(interaction, "7")

    @button(label="8", style=discord.ButtonStyle.grey, row=2)
    async def eight(self, interaction: discord.Interaction, button: Button):
        await self.update_value(interaction, "8")

    @button(label="9", style=discord.ButtonStyle.grey, row=2)
    async def nine(self, interaction: discord.Interaction, button: Button):
        await self.update_value(interaction, "9")

    @button(label="0", style=discord.ButtonStyle.grey, row=3)
    async def zero(self, interaction: discord.Interaction, button: Button):
        await self.update_value(interaction, "0")

    @button(label="+", style=discord.ButtonStyle.blurple, row=3)
    async def add(self, interaction: discord.Interaction, button: Button):
        await self.update_value(interaction, "+")

    @button(label="-", style=discord.ButtonStyle.blurple, row=3)
    async def subtract(self, interaction: discord.Interaction, button: Button):
        await self.update_value(interaction, "-")

    @button(label="*", style=discord.ButtonStyle.blurple, row=3)
    async def multiply(self, interaction: discord.Interaction, button: Button):
        await self.update_value(interaction, "*")

    @button(label="/", style=discord.ButtonStyle.blurple, row=3)
    async def divide(self, interaction: discord.Interaction, button: Button):
        await self.update_value(interaction, "/")

    @button(label="=", style=discord.ButtonStyle.green, row=4)
    async def equals(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.author:
            return await interaction.response.send_message(
                "This is not your embed.", ephemeral=True
            )
        try:
            expression = self.value.strip().replace("\n", "")
            result = str(safe_eval(expression))
            await self.update_embed(interaction, result)
            self.value = result  # Store the result for possible further calculations
        except (CalculationError, ZeroDivisionError, ArithmeticError, ValueError):
            await self.update_embed(interaction, "Error")

    @button(label="Clear", style=discord.ButtonStyle.red, row=4)
    async def clear(self, interaction: discord.Interaction, button: Button):
        await self.update_value(interaction, "Clear")

    async def update_value(self, interaction: discord.Interaction, value: str):
        # Check if the person interacting is the author of the embed
        if interaction.user != self.author:
            return await interaction.response.send_message(
                "This content does not appear to be part of your embedded materials.", ephemeral=True
            )
        # Append the value or clear if "Clear"
        if value == "Clear":
            self.value = ""
        else:
            self.value += value
        # Update the embed with the new value
        await self.update_embed(interaction, self.value)

    async def update_embed(self, interaction: discord.Interaction, result: str):
        content = f"**Calculator** | `{self.author.display_name}`\n```\n{result}\n```"
        await interaction.response.edit_message(content=content, view=self)
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
        view.message = await ctx.send(content="**Calculator**\n```\n \n```", view=view)

# Add the cog to the bot
def setup(bot):
    bot.add_cog(calculator(bot))

