from app.services.captcha.detection import CaptchaInfo, detect_captcha
from app.services.captcha.solver import CaptchaSolver, get_solver

__all__ = [
    "CaptchaInfo",
    "CaptchaSolver",
    "detect_captcha",
    "get_solver",
]
