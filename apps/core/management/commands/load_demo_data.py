"""
Full workflow seed: HOD needs, hostel 9-month project + monthly milestones, donors, July 2026 gala + media,
governance queue items. Idempotent by stable titles. Password demo123 (demo/demo for quick login).
"""
import base64
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.events.models import Event, EventMedia, EventRegistration
from apps.funding.models import Contribution, Expense, FundPool
from apps.needs.models import Need
from apps.projects.models import Milestone, Project, ProjectTeam
from apps.programs.models import Program, ProgramMilestone
from apps.stakeholders.models import Organization, UserProfile, UserRoleRequest
from apps.core.models import UploadAuditLog
from apps.stakeholders.persona_utils import replace_user_personas

User = get_user_model()
IST = ZoneInfo("Asia/Kolkata")

# 1×1 PNG for seeded “photos”
MINI_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _user(username, email, password, role, org=None):
    u, created = User.objects.get_or_create(username=username, defaults={"email": email})
    if created:
        u.set_password(password)
        u.save()
    prof = u.profile
    prof.stakeholder_type = role
    prof.organization = org
    prof.save()
    replace_user_personas(u, [role])
    return u


class Command(BaseCommand):
    help = "Seed workflow personas: HOD, lead, volunteer, donors, governance, finance + hostel project & July 2026 gala."

    @transaction.atomic
    def handle(self, *args, **options):
        Site.objects.update_or_create(
            pk=1, defaults={"domain": "localhost:8000", "name": "MSU Vision 2020"}
        )

        india, _ = FundPool.objects.get_or_create(
            jurisdiction=FundPool.Jurisdiction.INDIA,
            defaults={"name": "India CSR pool", "description": "India CSR"},
        )
        us_pool, _ = FundPool.objects.get_or_create(
            jurisdiction=FundPool.Jurisdiction.US,
            defaults={"name": "US 501(c)(3) pool", "description": "US"},
        )

        # Seed user-requested departments
        departments_list = [
            "Department of Applied Chemistry",
            "Department of Applied Mathematics",
            "Department of Applied Mechanics and Structural Engineering",
            "Department of Applied Physics",
            "Department of Architecture",
            "Department of Business Economics",
            "Department of Chemical Engineering",
            "Department of Civil Engineering",
            "Department of Computer Science and Engineering",
            "Department of Electrical Engineering",
            "Department of English",
            "Department of Mechanical Engineering",
            "Department of Metallurgical and Materials Engineering",
            "Department of Textile Chemistry",
            "Department of Textile Engineering",
            "Water Resources Engineering and Management Institute (WREMI)",
            
            # Additional departments for user's test plan
            "Computer Eng.",
            "Mechanical Eng.",
            "Applied Math",
            "Chemical Eng.",
            "Civil Eng.",
            "Electrical Eng.",
            "Electronics (ECE)",
            "Info. Tech (IT)",
        ]

        depts = {}
        for dept_name in departments_list:
            dept_obj, _ = Organization.objects.get_or_create(
                name=dept_name,
                defaults={
                    "org_type": Organization.OrgType.DEPARTMENT,
                    "jurisdiction": Organization.Jurisdiction.INDIA,
                }
            )
            depts[dept_name] = dept_obj

        org_hostel = depts["Department of Civil Engineering"]
        org_academic = depts["Department of Computer Science and Engineering"]

        admin = _user("admin", "admin@msu-vision.example", "demo123", UserProfile.StakeholderType.FOUNDATION_ADMIN)
        demo_u, _ = User.objects.get_or_create(username="demo", defaults={"email": "demo@local"})
        demo_u.set_password("demo")
        demo_u.save()
        demo_u.profile.stakeholder_type = UserProfile.StakeholderType.FOUNDATION_ADMIN
        demo_u.profile.needs_persona_assignment = False
        demo_u.profile.save()
        replace_user_personas(demo_u, [UserProfile.StakeholderType.FOUNDATION_ADMIN])

        finance = _user(
            "finance1", "finance@msu-vision.example", "demo123", UserProfile.StakeholderType.FINANCE_CONTROLLER
        )
        gov_meera = _user(
            "gov_meera", "governance@msu-vision.example", "demo123", UserProfile.StakeholderType.GOVERNANCE
        )
        hod_hostel = _user(
            "hod_hostel", "hod.hostel@msu-vision.example", "demo123", UserProfile.StakeholderType.HOD, org=org_hostel
        )
        hod_academic = _user(
            "hod_academic",
            "hod.academic@msu-vision.example",
            "demo123",
            UserProfile.StakeholderType.HOD,
            org=org_academic,
        )
        lead_hostel = _user(
            "lead_hostel", "lead.hostel@msu-vision.example", "demo123", UserProfile.StakeholderType.PROJECT_LEAD
        )
        volunteer_riya = _user(
            "volunteer_riya", "riya.vol@msu-vision.example", "demo123", UserProfile.StakeholderType.VOLUNTEER
        )
        donor_anita = _user(
            "donor_anita", "anita.donor@example.com", "demo123", UserProfile.StakeholderType.DONOR
        )
        donor_james = _user(
            "donor_james", "james.donor@example.com", "demo123", UserProfile.StakeholderType.DONOR
        )
        auditor = _user("auditor_kim", "audit@msu-vision.example", "demo123", UserProfile.StakeholderType.AUDITOR)
        hod_test = _user("hod_test", "hod.test@msu-vision.example", "Tester@123", UserProfile.StakeholderType.HOD)
        gov_test = _user("gov_test", "gov.test@msu-vision.example", "Tester@123", UserProfile.StakeholderType.GOVERNANCE)
        lead_test = _user("lead_test", "lead.test@msu-vision.example", "Tester@123", UserProfile.StakeholderType.PROJECT_LEAD)
        donor_test = _user("donor_test", "donor.test@msu-vision.example", "Tester@123", UserProfile.StakeholderType.DONOR)
        finance_test = _user("finance_test", "finance.test@msu-vision.example", "Tester@123", UserProfile.StakeholderType.FINANCE_CONTROLLER)
        volunteer_test = _user("volunteer_test", "volunteer.test@msu-vision.example", "Tester@123", UserProfile.StakeholderType.VOLUNTEER)
        auditor_test = _user("auditor_test", "auditor.test@msu-vision.example", "Tester@123", UserProfile.StakeholderType.AUDITOR)

        # --- HOD: draft need (academic) ---
        need_wifi, _ = Need.objects.get_or_create(
            title="Campus Wi-Fi upgrade — Phase 2 (draft)",
            defaults={
                "created_by": hod_academic,
                "department": org_academic,
                "description": "HOD priority: expand coverage in lecture blocks. Submit for foundation review when ready.",
                "status": Need.Status.DRAFT,
                "target_amount": Decimal("350000"),
                "target_currency": "INR",
                "requires_governance_approval": False,
            },
        )

        # --- Governance: high-value need awaiting approval ---
        need_gov, _ = Need.objects.get_or_create(
            title="Alumni Innovation & Research Wing",
            defaults={
                "created_by": hod_academic,
                "department": org_academic,
                "description": "Multi-year research floor; exceeds governance threshold for approval.",
                "status": Need.Status.PENDING_GOVERNANCE,
                "target_amount": Decimal("15000000"),
                "target_currency": "INR",
                "requires_governance_approval": True,
            },
        )

        # --- HOD hostel: matched need + flagship project ---
        need_hostel, _ = Need.objects.get_or_create(
            title="Boys Hostel Remodeling (2025–2026)",
            defaults={
                "created_by": hod_hostel,
                "department": org_hostel,
                "description": "Structural refresh, bathrooms, fire safety, and common room for 240 residents. "
                "Timeline ~9 months from kickoff.",
                "status": Need.Status.MATCHED,
                "funding_model": Need.FundingModel.POOLED,
                "target_amount": Decimal("8500000"),
                "target_currency": "INR",
                "requires_governance_approval": False,
            },
        )
        need_hostel.matched_donors.add(donor_anita, donor_james)

        proj_hostel, _ = Project.objects.get_or_create(
            need=need_hostel,
            title="Boys Hostel Remodeling Program",
            defaults={
                "lead": lead_hostel,
                "description": "Six–nine month delivery: civil, MEP, interiors, furniture, handover. "
                "Lead: alumni volunteer coordinator; Riya supports on-site checks.",
                "status": Project.Status.IN_PROGRESS,
                "budget": Decimal("8200000"),
                "budget_currency": "INR",
                "start_date": date(2025, 9, 1),
                "target_end_date": date(2026, 5, 31),
            },
        )
        if proj_hostel.title != need_hostel.title:
            proj_hostel.title = need_hostel.title
            proj_hostel.save(update_fields=["title"])
        ProjectTeam.objects.get_or_create(
            project=proj_hostel,
            user=volunteer_riya,
            defaults={"role": ProjectTeam.Role.VOLUNTEER},
        )

        monthly = [
            ("Sep 2025 — Kickoff & resident communication", Milestone.Status.DONE, date(2025, 9, 1), date(2025, 9, 28)),
            ("Oct 2025 — Structural & MEP design sign-off", Milestone.Status.DONE, date(2025, 10, 1), date(2025, 10, 31)),
            ("Nov 2025 — Tender, award & mobilization", Milestone.Status.DONE, date(2025, 11, 1), date(2025, 11, 30)),
            ("Dec 2025 — Demolition & shell civil", Milestone.Status.DONE, date(2025, 12, 1), date(2025, 12, 31)),
            ("Jan 2026 — Masonry, waterproofing", Milestone.Status.DONE, date(2026, 1, 1), date(2026, 1, 31)),
            ("Feb 2026 — Electrical & plumbing rough-in", Milestone.Status.DONE, date(2026, 2, 1), date(2026, 2, 28)),
            (
                "Mar 2026 — Interior phase: wet areas & corridors",
                Milestone.Status.IN_PROGRESS,
                date(2026, 3, 1),
                date(2026, 3, 31),
            ),
            ("Apr 2026 — Room interiors & fixtures", Milestone.Status.PENDING, date(2026, 4, 1), date(2026, 4, 30)),
            ("May 2026 — QA, furniture, handover & closeout", Milestone.Status.PENDING, date(2026, 5, 1), date(2026, 5, 31)),
        ]
        # % of project budget per milestone gate (need not sum to 100). Done + released = funded in rollup.
        hostel_tranche_pcts = [10, 10, 10, 10, 12, 12, 15, 10, 4]
        if not proj_hostel.milestones.exists():
            for seq, (title, st, sd, ed) in enumerate(monthly):
                pct = hostel_tranche_pcts[seq] if seq < len(hostel_tranche_pcts) else 0
                gov = Milestone.TrancheGovernance.NOT_APPLICABLE
                if pct > 0 and st == Milestone.Status.DONE:
                    gov = Milestone.TrancheGovernance.RELEASED
                Milestone.objects.create(
                    project=proj_hostel,
                    title=title,
                    description="",
                    start_date=sd,
                    due_date=ed,
                    status=st,
                    sequence=seq,
                    weight_percent=0,
                    completed_date=ed if st == Milestone.Status.DONE else None,
                    next_tranche_budget_percent=pct,
                    tranche_governance_status=gov,
                )

        for m in proj_hostel.milestones.filter(assigned_to__isnull=True):
            m.assigned_to = lead_hostel if m.sequence < 6 else volunteer_riya
            m.save(update_fields=["assigned_to"])

        # --- Project pending governance (USD budget over threshold) ---
        need_isc, _ = Need.objects.get_or_create(
            title="International Student Center (matched)",
            defaults={
                "created_by": admin,
                "department": org_academic,
                "description": "Feasibility cleared; project charter pending board sign-off.",
                "status": Need.Status.MATCHED,
                "target_amount": Decimal("200000"),
                "target_currency": "USD",
                "requires_governance_approval": False,
            },
        )
        proj_isc, _ = Project.objects.get_or_create(
            need=need_isc,
            title="International Student Center — Build",
            defaults={
                "lead": lead_hostel,
                "description": "High-budget build; requires governance approval on budget.",
                "status": Project.Status.PENDING_GOVERNANCE,
                "budget": Decimal("18500"),
                "budget_currency": "USD",
                "requires_governance_approval": True,
                "start_date": date(2026, 6, 1),
                "target_end_date": date(2027, 3, 31),
            },
        )
        if proj_isc.title != need_isc.title:
            proj_isc.title = need_isc.title
            proj_isc.save(update_fields=["title"])

        Project.objects.filter(pk=proj_hostel.pk).update(students_impacted=240)
        Project.objects.filter(pk=proj_isc.pk).update(students_impacted=800)

        # --- Contributions ---
        if not Contribution.objects.filter(donor=donor_anita, project=proj_hostel).exists():
            Contribution.objects.create(
                donor=donor_anita,
                project=proj_hostel,
                fund_pool=india,
                recorded_by=finance,
                amount=Decimal("4250000"),
                currency="INR",
                jurisdiction_origin=Contribution.JurisdictionOrigin.INDIA,
                status=Contribution.Status.RECEIVED,
                received_date=date(2025, 11, 10),
                notes="Pooled gift toward hostel remodeling",
            )
        if not Contribution.objects.filter(donor=donor_james, project=proj_hostel).exists():
            Contribution.objects.create(
                donor=donor_james,
                project=proj_hostel,
                fund_pool=us_pool,
                recorded_by=finance,
                amount=Decimal("12000"),
                currency="USD",
                jurisdiction_origin=Contribution.JurisdictionOrigin.US,
                status=Contribution.Status.RECEIVED,
                received_date=date(2025, 12, 5),
                notes="US chapter alumni gift",
            )

        # --- Expense: governance threshold (hostel) ---
        expense_gov, _ = Expense.objects.get_or_create(
            project=proj_hostel,
            description="Bulk sanitary & CP fittings — hostel block A–D",
            defaults={
                "fund_pool": india,
                "requested_by": lead_hostel,
                "amount": Decimal("320000"),
                "currency": "INR",
                "expense_date": date(2026, 3, 20),
                "status": Expense.Status.PENDING_GOVERNANCE,
                "requires_governance_approval": True,
            },
        )

        # --- July 2026 fundraising gala + plan + “photos” ---
        gala_desc = """## Roadmap to July 2026 gala

| When | Milestone |
|------|-----------|
| Jan 2026 | Steering committee & budget locked |
| Feb 2026 | Venue contract + catering shortlist |
| Mar 2026 | Save-the-date + alumni email series |
| Apr 2026 | Sponsor tiers & recognition packages |
| May 2026 | Ticket sales open (early bird) |
| Jun 2026 | Volunteer briefing, run-of-show dry run |
| **18 Jul 2026** | **Gala night — program, auction, donor recognition** |

Linked to **Boys Hostel Remodeling** for storytelling and impact updates to donors.
Post-event: thank-you, publish photos, reconcile pledges."""

        gala, _ = Event.objects.get_or_create(
            title="Hostel Renewal Gala & Donor Appreciation — July 2026",
            defaults={
                "organized_by": admin,
                "linked_project": proj_hostel,
                "linked_need": need_hostel,
                "description": gala_desc,
                "event_type": Event.EventType.FUNDRAISING,
                "venue": "MSU Foundation Auditorium",
                "location": "Campus — Main auditorium + foyer",
                "start_datetime": datetime(2026, 7, 18, 17, 30, tzinfo=IST),
                "end_datetime": datetime(2026, 7, 18, 22, 0, tzinfo=IST),
                "status": Event.Status.REGISTRATION_OPEN,
                "target_amount": Decimal("2500000"),
                "jurisdiction": Event.Jurisdiction.BOTH,
            },
        )

        if not Contribution.objects.filter(donor=donor_anita, event=gala).exists():
            Contribution.objects.create(
                donor=donor_anita,
                project=None,
                event=gala,
                fund_pool=india,
                recorded_by=finance,
                amount=Decimal("100000"),
                currency="INR",
                jurisdiction_origin=Contribution.JurisdictionOrigin.INDIA,
                status=Contribution.Status.PLEDGED,
                pledge_date=date(2026, 3, 1),
                notes="Table sponsorship pledge for July gala",
            )

        captions = [
            "Planning committee — Feb 2026 venue walkthrough",
            "Save-the-date creative (mock)",
            "Volunteer team briefing agenda — Jun 2026",
        ]
        for i, cap in enumerate(captions):
            if not gala.media_items.filter(caption=cap).exists():
                em = EventMedia(
                    event=gala,
                    uploaded_by=admin,
                    caption=cap,
                    media_type=EventMedia.MediaType.PHOTO,
                )
                em.file.save(f"gala_seed_{i}.png", ContentFile(MINI_PNG), save=True)

        EventRegistration.objects.get_or_create(
            event=gala,
            user=donor_anita,
            defaults={"role": EventRegistration.Role.ATTENDEE},
        )
        EventRegistration.objects.get_or_create(
            event=gala,
            user=donor_james,
            defaults={"role": EventRegistration.Role.ATTENDEE},
        )

        from apps.events.models import EventMilestone
        EventMilestone.objects.get_or_create(
            event=gala,
            title="Venue deposit paid",
            defaults={
                "due_date": date(2026, 2, 28),
                "completed": True,
                "completed_date": date(2026, 2, 25),
                "owner": admin
            }
        )
        EventMilestone.objects.get_or_create(
            event=gala,
            title="Publish sponsor packages",
            defaults={
                "due_date": date(2026, 4, 15),
                "completed": False,
                "owner": admin
            }
        )

        prog_hostel, _ = Program.objects.get_or_create(
            title="Hostel Modernization Initiative",
            defaults={
                "description": "Umbrella program for all hostel renovations.",
                "fund_pool": india,
                "budget": Decimal("50000000"),
                "budget_currency": "INR",
                "start_date": date(2025, 1, 1),
                "end_date": date(2028, 12, 31),
                "status": Program.Status.ACTIVE,
                "originated_by": hod_hostel,
            }
        )
        prog_hostel.owners.set([hod_hostel, lead_hostel])
        if proj_hostel.program != prog_hostel:
            proj_hostel.program = prog_hostel
            proj_hostel.save(update_fields=["program"])

        ProgramMilestone.objects.get_or_create(
            program=prog_hostel,
            title="Boys Hostel Block A Funding Secured",
            defaults={
                "phase": "Funding",
                "due_date": date(2025, 12, 31),
                "completed": True,
                "owner": lead_hostel,
                "tranche_percent": 20
            }
        )

        UserRoleRequest.objects.get_or_create(
            user=volunteer_riya,
            requested_persona=UserProfile.StakeholderType.PROJECT_LEAD,
            defaults={
                "reason": "Requesting lead role for upcoming project.",
                "status": UserRoleRequest.Status.PENDING
            }
        )
        UserRoleRequest.objects.get_or_create(
            user=demo_u,
            requested_persona=UserProfile.StakeholderType.GOVERNANCE,
            defaults={
                "reason": "Approved for governance.",
                "status": UserRoleRequest.Status.APPROVED,
                "reviewed_by": admin,
                "reviewed_at": timezone.now()
            }
        )

        UploadAuditLog.objects.get_or_create(
            filename="anita-hostel-80g-letter.pdf",
            uploader=admin,
            defaults={
                "upload_type": "communication_capture",
                "file_size": 250000,
                "actual_mime": "application/pdf",
                "scan_result": UploadAuditLog.ScanResult.CLEAN,
                "action_taken": UploadAuditLog.ActionTaken.ACCEPTED
            }
        )

        # Stewardship / receipt / comms capture (idempotent updates)
        Contribution.objects.filter(donor=donor_anita, project=proj_hostel).update(
            receipt_sent=True,
            receipt_sent_date=date(2025, 11, 18),
            communication_capture_url="https://msu-vision-demo.s3.amazonaws.com/comms/anita-hostel-80g-letter.pdf",
            volunteer_lead=lead_hostel,
        )
        Contribution.objects.filter(donor=donor_james, project=proj_hostel).update(
            receipt_sent=False,
            receipt_sent_date=None,
            volunteer_lead=volunteer_riya,
        )
        Contribution.objects.filter(donor=donor_anita, event=gala).update(volunteer_lead=lead_hostel)

        # Owners (registered users only; idempotent .set)
        need_wifi.owners.set([hod_academic])
        need_gov.owners.set([hod_academic, gov_meera])
        need_hostel.owners.set([hod_hostel, lead_hostel])
        need_isc.owners.set([hod_academic, gov_meera])
        proj_hostel.owners.set([lead_hostel, hod_hostel, finance])
        proj_isc.owners.set([lead_hostel, gov_meera])
        for m in proj_hostel.milestones.all():
            uids = [lead_hostel.pk]
            if m.assigned_to_id:
                uids.append(m.assigned_to_id)
            m.owners.set(list(dict.fromkeys(uids)))
        expense_gov.owners.set([lead_hostel, finance])

        self.stdout.write(
            self.style.SUCCESS(
                "\n=== Seed complete (password demo123 unless noted) ===\n"
                "• demo — password demo (Foundation admin quick login)\n"
                "• hod_hostel — Create/edit hostel needs; matched need + project exist\n"
                "• hod_academic — Draft need (Wi-Fi phase 2)\n"
                "• lead_hostel — Boys hostel project + monthly milestones\n"
                "• volunteer_riya — On project team for hostel\n"
                "• donor_anita / donor_james — Contributions + July gala pledge/registration\n"
                "• gov_meera — Governance queue: research wing need, ISC project, large expense\n"
                "• finance1 — Record funding; approve standard expenses\n"
                "• auditor_kim — Read-only visibility\n"
                "• admin — Full access\n\n"
                "Open Events for the July 2026 gala (schedule + seeded photos).\n"
            )
        )
