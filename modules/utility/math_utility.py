## ComfyUI/custom_nodes/ComfyPanel/modules/utility/math_utility.py

import math

def math_operation_calc(operation, A, B, precision=-1):
    unary_ops = ["sin", "cos", "tan", "sqrt", "exp", "log", "neg", "abs"]

    if not isinstance(precision, int):
        raise ValueError("Precision must be an integer")
    if precision > 100:
        raise ValueError("Precision too high, must be <= 100")

    try:
        if operation in unary_ops:
            B = 0.0
            if operation == "sqrt" and A < 0:
                raise ValueError("sqrt input must be >= 0")
            if operation == "log" and A <= 0:
                raise ValueError("log input must be > 0")
            if operation == "tan" and math.cos(A) == 0:
                raise ValueError("tan is undefined at this input")
            result = {
                "sin": math.sin(A),
                "cos": math.cos(A),
                "tan": math.tan(A),
                "sqrt": math.sqrt(A),
                "exp": math.exp(A),
                "log": math.log(A),
                "neg": -A,
                "abs": abs(A)
            }[operation]
        else:
            if operation == "add": result = A + B
            elif operation == "subtract": result = A - B
            elif operation == "multiply": result = A * B
            elif operation == "divide": result = A / B if B != 0 else float("inf")
            elif operation == "modulo": result = A % B if B != 0 else float("nan")
            elif operation == "power": result = A ** B
            else: raise ValueError(f"Unknown operation: {operation}")

        float_result = round(result, precision) if precision >= 0 else result
        int_result = int(result)
        return float_result, int_result

    except Exception as e:
        print(f"[MathOperation Error] {e}")
        return 0.0, 0
