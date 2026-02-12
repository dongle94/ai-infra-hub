"""
안전한 수식 계산기 Tool (Open WebUI용)

Open WebUI의 Tool 등록 형식에 맞춘 수학 수식 평가 도구.
보안을 위해 eval()/exec()를 사용하지 않고, Python ast 모듈 기반의
화이트리스트 방식 안전 평가기를 구현한다.

지원 연산: +, -, *, /, //, %, ** (거듭제곱), 괄호
지원 함수: sqrt, sin, cos, tan, asin, acos, atan, log, log2, log10,
          abs, round, pow, ceil, floor, factorial
지원 상수: pi, e
"""

import ast
import math
import operator
from typing import Any, Union

# ---------------------------------------------------------------------------
# 안전한 수식 평가기 (Safe Expression Evaluator)
# ---------------------------------------------------------------------------
# eval()을 사용하지 않는다. ast.parse()로 파싱된 AST 트리를 직접 순회하며
# 화이트리스트에 등록된 노드 타입과 연산만 허용한다.
# ---------------------------------------------------------------------------

# 허용되는 이항 연산자 매핑
_BINARY_OPERATORS: dict[type, Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

# 허용되는 단항 연산자 매핑
_UNARY_OPERATORS: dict[type, Any] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

# 허용되는 수학 함수 매핑 (이름 -> 호출 가능 객체)
_SAFE_FUNCTIONS: dict[str, Any] = {
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "log": math.log,
    "log2": math.log2,
    "log10": math.log10,
    "abs": abs,
    "round": round,
    "pow": pow,
    "ceil": math.ceil,
    "floor": math.floor,
    "factorial": math.factorial,
}

# 허용되는 수학 상수 매핑
_SAFE_CONSTANTS: dict[str, Union[int, float]] = {
    "pi": math.pi,
    "e": math.e,
}

# 허용되는 AST 노드 타입 집합
_ALLOWED_NODE_TYPES: set[type] = {
    ast.Expression,
    ast.Constant,
    ast.BinOp,
    ast.UnaryOp,
    ast.Call,
    ast.Name,
    ast.Load,
}

# 보안 제한값
_MAX_EXPRESSION_LENGTH = 500
_MAX_EXPONENT = 10000
_MAX_FACTORIAL_INPUT = 170


class _SafeEvaluationError(Exception):
    """안전 평가기 내부 오류."""
    pass


def _safe_eval_node(node: ast.AST) -> Union[int, float]:
    """AST 노드를 재귀적으로 평가한다. 화이트리스트 외 노드는 즉시 거부."""
    if type(node) not in _ALLOWED_NODE_TYPES:
        raise _SafeEvaluationError(
            f"허용되지 않은 구문입니다: {type(node).__name__}"
        )

    if isinstance(node, ast.Expression):
        return _safe_eval_node(node.body)

    if isinstance(node, ast.Constant):
        # bool은 int의 서브클래스이므로 선행 검사로 명시적 거부
        if isinstance(node.value, bool):
            raise _SafeEvaluationError(
                "True/False는 수식에서 사용할 수 없습니다. 숫자만 입력하세요."
            )
        if isinstance(node.value, (int, float)):
            return node.value
        raise _SafeEvaluationError(
            f"허용되지 않은 상수 타입입니다: {type(node.value).__name__}"
        )

    if isinstance(node, ast.Name):
        name = node.id
        if name in _SAFE_CONSTANTS:
            return _SAFE_CONSTANTS[name]
        if name in _SAFE_FUNCTIONS:
            raise _SafeEvaluationError(
                f"'{name}'은 함수입니다. '{name}(값)' 형태로 사용하세요."
            )
        raise _SafeEvaluationError(
            f"알 수 없는 식별자입니다: '{name}'. "
            f"사용 가능한 상수: {', '.join(sorted(_SAFE_CONSTANTS.keys()))}"
        )

    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _BINARY_OPERATORS:
            raise _SafeEvaluationError(
                f"허용되지 않은 연산자입니다: {op_type.__name__}"
            )
        left = _safe_eval_node(node.left)
        right = _safe_eval_node(node.right)

        if op_type is ast.Pow:
            if isinstance(right, (int, float)) and abs(right) > _MAX_EXPONENT:
                raise _SafeEvaluationError(
                    f"지수가 너무 큽니다: {right}. 최대 허용 지수: {_MAX_EXPONENT}"
                )

        if op_type in (ast.Div, ast.FloorDiv, ast.Mod):
            if right == 0:
                raise _SafeEvaluationError("0으로 나눌 수 없습니다.")

        op_func = _BINARY_OPERATORS[op_type]
        return op_func(left, right)

    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _UNARY_OPERATORS:
            raise _SafeEvaluationError(
                f"허용되지 않은 단항 연산자입니다: {op_type.__name__}"
            )
        operand = _safe_eval_node(node.operand)
        op_func = _UNARY_OPERATORS[op_type]
        return op_func(operand)

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise _SafeEvaluationError(
                "메서드 호출이나 중첩 속성 접근은 허용되지 않습니다. "
                "직접 함수 이름만 사용하세요 (예: sqrt, sin, log)."
            )
        func_name = node.func.id
        if func_name not in _SAFE_FUNCTIONS:
            raise _SafeEvaluationError(
                f"허용되지 않은 함수입니다: '{func_name}'. "
                f"사용 가능한 함수: {', '.join(sorted(_SAFE_FUNCTIONS.keys()))}"
            )

        if node.keywords:
            raise _SafeEvaluationError(
                "키워드 인자(keyword arguments)는 지원되지 않습니다."
            )

        args = [_safe_eval_node(arg) for arg in node.args]

        if func_name == "factorial":
            if len(args) != 1:
                raise _SafeEvaluationError(
                    "factorial()은 정확히 1개의 인자가 필요합니다."
                )
            if not isinstance(args[0], int) and not (
                isinstance(args[0], float) and args[0].is_integer()
            ):
                raise _SafeEvaluationError(
                    "factorial()은 음이 아닌 정수만 허용합니다."
                )
            if args[0] < 0:
                raise _SafeEvaluationError(
                    "factorial()은 음이 아닌 정수만 허용합니다."
                )
            int_val = int(args[0])
            if int_val > _MAX_FACTORIAL_INPUT:
                raise _SafeEvaluationError(
                    f"factorial 입력이 너무 큽니다: {int_val}. "
                    f"최대 허용값: {_MAX_FACTORIAL_INPUT}"
                )
            return math.factorial(int_val)

        func = _SAFE_FUNCTIONS[func_name]
        return func(*args)

    raise _SafeEvaluationError(
        f"처리할 수 없는 구문입니다: {type(node).__name__}"
    )


def safe_evaluate(expression: str) -> Union[int, float]:
    """수학 수식 문자열을 안전하게 평가한다 (eval 미사용)."""
    if len(expression) > _MAX_EXPRESSION_LENGTH:
        raise _SafeEvaluationError(
            f"수식이 너무 깁니다 (최대 {_MAX_EXPRESSION_LENGTH}자). "
            f"현재 길이: {len(expression)}자"
        )

    # ^ 연산자를 ** 로 변환 (사용자 편의)
    expression_normalized = expression.replace("^", "**")

    tree = ast.parse(expression_normalized, mode="eval")
    result = _safe_eval_node(tree)

    if isinstance(result, float):
        if math.isinf(result):
            raise _SafeEvaluationError("계산 결과가 무한대(infinity)입니다.")
        if math.isnan(result):
            raise _SafeEvaluationError("계산 결과가 숫자가 아닙니다(NaN).")

    return result


def _format_result(value: Union[int, float]) -> str:
    """계산 결과를 보기 좋은 문자열로 포맷한다."""
    if isinstance(value, int):
        return str(value)
    # 매우 큰 수는 과학적 표기법 사용 (300자+ 문자열 방지)
    if abs(value) >= 1e15:
        return f"{value:.6e}"
    if value == int(value):
        return str(int(value))
    formatted = f"{value:.10f}".rstrip("0").rstrip(".")
    return formatted


# ---------------------------------------------------------------------------
# Open WebUI Tool 클래스
# ---------------------------------------------------------------------------


class Tools:
    """Open WebUI용 수학 계산기 Tool."""

    def __init__(self):
        """Tool 초기화."""
        pass

    def calculate(self, expression: str) -> str:
        """
        수학 수식을 안전하게 계산합니다. eval()을 사용하지 않는 보안 평가기입니다.
        Safely evaluates a mathematical expression without using eval().
        Use this tool when the user asks to calculate, compute, or evaluate
        a math expression.

        지원 연산: +, -, *, /, //(정수 나눗셈), %(나머지), **(거듭제곱), 괄호
        지원 함수: sqrt, sin, cos, tan, asin, acos, atan, log, log2, log10,
                  abs, round, pow, ceil, floor, factorial
        지원 상수: pi, e

        :param expression: The mathematical expression to evaluate
                          (e.g., "3.14 * 5**2", "sqrt(144)", "sin(pi/4)")
        """
        if not expression or not expression.strip():
            return (
                "[계산 오류] 수식이 비어 있습니다. "
                "계산할 수식을 입력하세요. (예: 2 + 3, sqrt(16), pi * 5**2)"
            )

        expression = expression.strip()

        try:
            result = safe_evaluate(expression)
            formatted = _format_result(result)
            return f"{expression} = {formatted}"

        except _SafeEvaluationError as exc:
            return f'[계산 오류] {exc} | 입력된 수식: "{expression}"'
        except SyntaxError:
            return (
                f'[구문 오류] 수식의 문법이 올바르지 않습니다. | '
                f'입력된 수식: "{expression}" | '
                f'올바른 예시: "2 + 3", "sqrt(16)", "3.14 * 5**2"'
            )
        except ZeroDivisionError:
            return f'[계산 오류] 0으로 나눌 수 없습니다. | 입력된 수식: "{expression}"'
        except OverflowError:
            return f'[계산 오류] 계산 결과가 너무 큽니다 (오버플로우). | 입력된 수식: "{expression}"'
        except ValueError as exc:
            return f'[계산 오류] 잘못된 값입니다: {exc} | 입력된 수식: "{expression}"'
        except TypeError as exc:
            return f'[계산 오류] 인자 타입 또는 개수가 올바르지 않습니다: {exc} | 입력된 수식: "{expression}"'
        except Exception as exc:
            return (
                f"[계산 오류] 예기치 않은 오류: {type(exc).__name__}: {exc} | "
                f'입력된 수식: "{expression}"'
            )
