import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from app.bot.date_picker import date_rows, date_text

class DatePickerTests(unittest.TestCase):
    def test_local_today_and_month_boundary(self):
        with patch('app.bot.date_picker.utcnow', return_value=datetime(2026, 10, 31, 23, 30, tzinfo=timezone.utc)):
            rows=date_rows('Europe/Kyiv')
        self.assertEqual(rows[0][0][1], 'pickdate_2026-11-01')
        self.assertEqual(rows[0][1][1], 'pickdate_2026-11-02')
        self.assertEqual(rows[-1][-1][1], 'pickdays_14')

    def test_later_dates_and_back(self):
        with patch('app.bot.date_picker.utcnow', return_value=datetime(2026, 12, 25, tzinfo=timezone.utc)):
            rows=date_rows('Europe/Kyiv',14)
        self.assertEqual(rows[0][0][1], 'pickdate_2027-01-08')
        self.assertEqual(rows[-1][0][1], 'pickdays_0')

    def test_custom_time_uses_selected_date(self):
        self.assertEqual(date_text('17:20', {'picked_date':'2026-11-03'}),'03.11.2026 17:20')
        self.assertEqual(date_text('04.11.2026 16:00', {'picked_date':'2026-11-03'}),'04.11.2026 16:00')
