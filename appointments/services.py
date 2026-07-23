"""Business logic for the appointments app."""

from datetime import date, datetime, timedelta

from django.utils import timezone

from doctors.models import Doctor, DoctorAvailability

from .models import Appointment, AppointmentManager


def available_slots(doctor: Doctor, on_date: date) -> list[dict]:
    """
    Return list of available time slots for a doctor on a given date.
    Each slot: {"value": "HH:MM", "label": "H:MM AM/PM"}.

    A slot is available if:
      - It falls entirely within one of the doctor's availability windows
        for that weekday.
      - It doesn't overlap any active (scheduled/confirmed/in-progress) appointment.
      - It isn't in the past (when on_date is today).
    """
    weekday = on_date.weekday()
    duration = timedelta(minutes=doctor.consultation_duration_minutes)

    # 1. All availability windows for this weekday
    windows = DoctorAvailability.objects.filter(doctor=doctor, weekday=weekday).order_by(
        "start_time"
    )

    if not windows:
        return []

    # 2. All active appointments already booked on this date
    day_start_naive = datetime.combine(on_date, datetime.min.time())
    day_end_naive = day_start_naive + timedelta(days=1)
    day_start = timezone.make_aware(day_start_naive)
    day_end = timezone.make_aware(day_end_naive)

    booked = list(
        Appointment.objects.filter(
            doctor=doctor,
            status__in=AppointmentManager.ACTIVE_STATUSES,
            scheduled_start__gte=day_start,
            scheduled_start__lt=day_end,
        ).values_list("scheduled_start", "scheduled_end")
    )

    now = timezone.now()
    slots = []

    for window in windows:
        # Build datetime for the start/end of this window
        slot_start = timezone.make_aware(datetime.combine(on_date, window.start_time))
        window_end = timezone.make_aware(datetime.combine(on_date, window.end_time))

        while slot_start + duration <= window_end:
            slot_end = slot_start + duration

            # Skip past slots
            if slot_end <= now:
                slot_start = slot_end
                continue

            # Skip overlapping slots
            overlaps = any(b_start < slot_end and b_end > slot_start for b_start, b_end in booked)
            if not overlaps:
                local = timezone.localtime(slot_start)
                slots.append(
                    {
                        "value": local.strftime("%H:%M"),
                        "label": local.strftime("%I:%M %p").lstrip("0"),
                    }
                )

            slot_start = slot_end

    return slots
