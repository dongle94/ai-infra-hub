"""
Open WebUI Tool: 현재 날짜/시간 조회

한국 표준시(KST, UTC+9) 기준으로 현재 날짜와 시각을 반환하는 Tool.
Open WebUI의 Workspace > Tools 에디터에 그대로 복사하여 등록할 수 있습니다.
"""

from datetime import datetime, timezone, timedelta


class Tools:
    """현재 날짜와 시각을 조회하는 Open WebUI Tool."""

    KST_OFFSET = timedelta(hours=9)
    KST = timezone(KST_OFFSET)
    WEEKDAY_KR = ("월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일")

    def __init__(self):
        """Tool 초기화."""
        pass

    def get_current_datetime(self) -> str:
        """
        현재 날짜와 시각을 한국 표준시(KST) 기준으로 반환합니다.
        Returns the current date and time in Korea Standard Time (KST, UTC+9).
        Use this tool when the user asks about the current time, date, day of the week,
        or any time-related question.
        """
        try:
            now_kst = datetime.now(tz=self.KST)
            weekday_kr = self.WEEKDAY_KR[now_kst.weekday()]
            return now_kst.strftime(f"%Y-%m-%d %H:%M:%S (KST, {weekday_kr})")
        except Exception as e:
            return f"[오류] 현재 시각을 가져오는 데 실패했습니다: {type(e).__name__}: {e}"
