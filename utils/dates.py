import datetime

def get_today() -> datetime.date:
    return datetime.date.today()

def get_current_month_range() -> tuple[datetime.date, datetime.date]:
    today = get_today()
    start = today.replace(day=1)
    # compute end of month
    next_month = start.replace(day=28) + datetime.timedelta(days=4)
    end = next_month - datetime.timedelta(days=next_month.day)
    return start, end

def format_date_human(d) -> str:
    if isinstance(d, datetime.datetime):
        d = d.date()
    today = get_today()
    if d == today:
        return "Today"
    elif d == today - datetime.timedelta(days=1):
        return "Yesterday"
    return d.strftime("%d %b, %Y")
