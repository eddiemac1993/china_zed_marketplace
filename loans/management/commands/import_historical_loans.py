"""Seed the loan book with the historical WhatsApp loan register.

Idempotent: every row is tagged ``[hist#N]`` in its notes, so re-running the
command skips rows that are already present. Dates that were only known to the
month are anchored to the 1st; unknown due dates are derived from the period
implied by the interest rate.
"""
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from loans.models import Loan, LoanCustomer, LoanTopUp

# interest rate -> loan period in weeks (matches the default LoanSettings ladder)
RATE_TO_WEEKS = {20: 1, 15: 2, 30: 2, 35: 3, 45: 4}

# (hist#, issue_date, borrower, amount, rate%, type, due_date|None, notes)
REGISTER = [
    (1, "2026-07-21", "Jalata Moses", 500, 35, "new", "2026-08-04", "First loan"),
    (2, "2026-07-25", "Maina Sibanda", 600, 15, "new", None, ""),
    (3, "2026-07-25", "Violet", 500, 15, "new", None, ""),
    (4, "2026-07-30", "Maina Sibanda", 500, 15, "topup", None, "Top-up for existing customer"),
    (5, "2026-08-01", "Pauline", 50, 20, "new", None, "Month known, exact day pending"),
    (6, "2026-08-01", "Mwandu Gerald", 300, 45, "new", None, "Month known, exact day pending"),
    (7, "2026-08-01", "Mambwe Mumba", 1200, 45, "new", None, "Month known, exact day pending"),
    (8, "2026-08-01", "Chisala Kaunda", 1200, 45, "new", None, "Month known, exact day pending"),
    (9, "2026-08-01", "Moses Phiri", 510, 35, "new", None, "Month known, exact day pending"),
    (10, "2026-08-01", "Annie Soko", 200, 35, "new", None, "Month known, exact day pending"),
    (11, "2026-08-01", "Royda", 400, 35, "new", None, "Month known, exact day pending"),
    (12, "2026-08-01", "Abigail Moonga", 500, 45, "new", None, "Month known, exact day pending"),
    (13, "2026-08-01", "Chisomo Banda", 250, 35, "new", None, "Single K250 advance (register row 13+14 merged)"),
    # 14: removed - the reconstructed K250 top-up was wrong, Chisomo only got K250 total.
    (15, "2026-08-01", "Natasha", 650, 30, "new", None, "Month known, exact day pending"),
    (16, "2026-09-03", "Dominic", 100, 35, "new", None, "Recorded 03-Sep-2026"),
    (17, "2026-08-28", "Tama", 500, 20, "new", None, ""),
]


class Command(BaseCommand):
    help = "Import the historical loan register (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        created_loans = created_topups = skipped = 0

        for hist, issue_s, name, amount, rate, kind, due_s, note in REGISTER:
            tag = f"[hist#{hist}]"
            amount = Decimal(str(amount))
            rate = Decimal(str(rate))
            issue = date.fromisoformat(issue_s)
            weeks = RATE_TO_WEEKS.get(int(rate), 4)
            full_note = f"{tag} {note}".strip()

            customer, made = LoanCustomer.objects.get_or_create(full_name=name)
            if made and not dry_run:
                self.stdout.write(f"  + customer {name}")

            if kind == "topup":
                if LoanTopUp.objects.filter(note__contains=tag).exists():
                    skipped += 1
                    continue
                base = (
                    Loan.objects.filter(customer=customer)
                    .order_by("issue_date", "id")
                    .first()
                )
                if not base:
                    self.stderr.write(
                        self.style.WARNING(f"  ! {tag} {name}: no base loan to top up, skipping")
                    )
                    continue
                if dry_run:
                    self.stdout.write(f"  ~ {tag} top-up K{amount} on {base.reference} ({name})")
                    created_topups += 1
                    continue
                base.add_topup(amount=amount, user=None, note=full_note, date=issue)
                created_topups += 1
                self.stdout.write(
                    self.style.SUCCESS(f"  + {tag} top-up K{amount} -> {base.reference} ({name})")
                )
                continue

            if Loan.objects.filter(notes__contains=tag).exists():
                skipped += 1
                continue
            if dry_run:
                self.stdout.write(
                    f"  ~ {tag} loan K{amount} @ {rate}% ({name}), {weeks}wk from {issue}"
                )
                created_loans += 1
                continue

            loan = Loan(
                customer=customer,
                original_principal=amount,
                principal=amount,
                interest_rate=rate,
                period_weeks=weeks,
                issue_date=issue,
                payment_method=Loan.CASH,
                notes=full_note,
            )
            if due_s:
                loan.due_date = date.fromisoformat(due_s)
            loan.save()
            loan.refresh_status()
            created_loans += 1
            self.stdout.write(
                self.style.SUCCESS(
                    f"  + {tag} {loan.reference} K{amount} @ {rate}% -> {name} "
                    f"(due {loan.due_date}, {loan.get_status_display()})"
                )
            )

        summary = (
            f"{created_loans} loan(s), {created_topups} top-up(s) "
            f"{'to import' if dry_run else 'imported'}; {skipped} already present."
        )
        self.stdout.write(self.style.MIGRATE_HEADING(summary))
        if dry_run:
            transaction.set_rollback(True)
