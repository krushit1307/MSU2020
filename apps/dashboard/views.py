from datetime import timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import redirect_to_login as auth_redirect_login
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.views.generic import TemplateView

from apps.core.currency_utils import convert_usd_amount, exchange_rate_context, usd_to_inr_rate
from apps.core.permissions import has_stakeholder_type, user_stakeholder_codes
from apps.projects.models import Milestone
from apps.events.models import Event
from apps.funding.models import Contribution, Expense
from apps.needs.models import Need
from apps.needs.visibility import filter_needs_for_user, filter_projects_for_user
from apps.projects.funding_gates import milestones_awaiting_funding_release, project_funding_gate_metrics
from apps.projects.models import Project, ProjectTeam
from apps.projects.progress import calculate_project_progress
from apps.dashboard import roster, scorecard
from apps.stakeholders.models import UserProfile
from apps.stakeholders.persona_utils import apply_profile_bulk_rows, parse_profile_upload_csv, sample_csv_text


class HomeView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        u = self.request.user
        profile = getattr(u, "profile", None)
        codes = user_stakeholder_codes(u)
        ctx["persona_codes"] = sorted(codes)
        ctx["role_display"] = profile.persona_display() if profile else ""
        ctx["stakeholder_type"] = profile.stakeholder_type if profile else None
        sc = scorecard.organization_scorecard()
        display_currency = self.request.session.get("display_currency", "USD")
        if display_currency not in ("USD", "INR"):
            display_currency = "USD"
        ctx["display_currency"] = display_currency
        ctx["currency_symbol"] = "₹" if display_currency == "INR" else "$"
        ctx.update(exchange_rate_context())
        ctx["scorecard"] = {
            **sc,
            "donations_collected": convert_usd_amount(sc["donations_collected_usd"], display_currency),
            "donations_pledged": convert_usd_amount(sc["donations_pledged_usd"], display_currency),
        }
        ctx["recent_needs"] = filter_needs_for_user(Need.objects.all(), u)[:6]
        ctx["recent_projects"] = filter_projects_for_user(
            Project.objects.select_related("lead", "need"), u
        )[:6]

        ctx["show_governance_tile"] = u.is_superuser or codes & {
            UserProfile.StakeholderType.GOVERNANCE,
            UserProfile.StakeholderType.FOUNDATION_ADMIN,
        }

        open_event_status = [
            Event.Status.PUBLISHED,
            Event.Status.REGISTRATION_OPEN,
            Event.Status.ONGOING,
        ]
        if u.is_superuser or codes & {
            UserProfile.StakeholderType.FOUNDATION_ADMIN,
            UserProfile.StakeholderType.FINANCE_CONTROLLER,
            UserProfile.StakeholderType.GOVERNANCE,
            UserProfile.StakeholderType.AUDITOR,
        }:
            ctx["upcoming_events"] = Event.objects.filter(
                start_datetime__gte=timezone.now() - timedelta(days=1),
                status__in=open_event_status + [Event.Status.DRAFT],
            ).order_by("start_datetime")[:5]
        else:
            ctx["upcoming_events"] = Event.objects.filter(
                start_datetime__gte=timezone.now() - timedelta(days=1),
                status__in=open_event_status,
            ).order_by("start_datetime")[:5]

        ctx["gov_pending_total"] = 0
        if ctx["show_governance_tile"]:
            ctx["gov_pending_total"] = (
                Need.objects.filter(status=Need.Status.PENDING_GOVERNANCE).count()
                + Project.objects.filter(status=Project.Status.PENDING_GOVERNANCE).count()
                + Expense.objects.filter(status=Expense.Status.PENDING_GOVERNANCE).count()
            )

        ctx["can_create_need"] = u.is_superuser or codes & {
            UserProfile.StakeholderType.HOD,
            UserProfile.StakeholderType.FOUNDATION_ADMIN,
        }
        ctx["draft_need_count"] = 0
        if UserProfile.StakeholderType.HOD in codes or u.is_superuser:
            ctx["draft_need_count"] = filter_needs_for_user(Need.objects.filter(status=Need.Status.DRAFT), u).count()

        ctx["lead_projects"] = []
        if UserProfile.StakeholderType.PROJECT_LEAD in codes or u.is_superuser:
            qs = filter_projects_for_user(
                Project.objects.filter(lead=u).select_related("need").prefetch_related("milestones"), u
            )[:5]
            for p in qs:
                ctx["lead_projects"].append(
                    {
                        "project": p,
                        "progress_pct": calculate_project_progress(p),
                        "next_ms": p.milestones.exclude(status="done")
                        .exclude(status="cancelled")
                        .order_by("due_date")
                        .first(),
                    }
                )

        ctx["volunteer_projects"] = []
        if UserProfile.StakeholderType.VOLUNTEER in codes:
            pids = ProjectTeam.objects.filter(user=u).values_list("project_id", flat=True)
            for p in (
                filter_projects_for_user(Project.objects.filter(pk__in=pids).select_related("need"), u)
            )[:5]:
                ctx["volunteer_projects"].append(
                    {"project": p, "progress_pct": calculate_project_progress(p)}
                )

        ctx["donor_portfolio"] = []
        ctx["donor_contributions"] = []
        if UserProfile.StakeholderType.DONOR in codes:
            contribs = Contribution.objects.filter(donor=u).select_related("project", "event", "fund_pool")
            ctx["donor_contributions"] = list(contribs.order_by("-created_at")[:10])
            seen = set()
            for c in contribs:
                if c.project_id and c.project_id not in seen:
                    seen.add(c.project_id)
                    p = c.project
                    total_ms = p.milestones.exclude(status="cancelled").count()
                    done_ms = p.milestones.filter(status="done").count()
                    ctx["donor_portfolio"].append(
                        {
                            "project": p,
                            "progress_pct": calculate_project_progress(p),
                            "milestones_done": done_ms,
                            "milestones_total": total_ms,
                        }
                    )

        ctx["finance_pending_expenses"] = 0
        if u.is_superuser or codes & {
            UserProfile.StakeholderType.FOUNDATION_ADMIN,
            UserProfile.StakeholderType.FINANCE_CONTROLLER,
        }:
            ctx["finance_pending_expenses"] = Expense.objects.filter(status=Expense.Status.PENDING).count()

        return ctx


class ProjectRollupView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/project_rollup.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        projects = list(
            filter_projects_for_user(
                Project.objects.select_related("lead", "need").prefetch_related("milestones"),
                self.request.user,
            )
        )
        today = timezone.localdate()
        stalled_cutoff = today - timedelta(days=14)
        rows = []
        for p in projects:
            pct = calculate_project_progress(p)
            overdue = p.milestones.filter(status="overdue").count()
            tranche_pending = p.milestones.filter(
                tranche_governance_status=Milestone.TrancheGovernance.AWAITING_GOVERNANCE
            ).count()
            is_stalled = False
            stalled_days = 0
            if p.status == Project.Status.IN_PROGRESS and pct == 0:
                ref_date = p.updated_at.date() if p.updated_at else p.created_at.date()
                if ref_date <= stalled_cutoff:
                    is_stalled = True
                    stalled_days = (today - ref_date).days
            rows.append(
                {
                    "project": p,
                    "progress_pct": pct,
                    "overdue_count": overdue,
                    "tranche_pending_count": tranche_pending,
                    "is_stalled": is_stalled,
                    "stalled_days": stalled_days,
                    "funding_gate_metrics": project_funding_gate_metrics(p),
                }
            )
        ctx["rows"] = rows
        codes = user_stakeholder_codes(self.request.user)
        ctx["show_programs_section"] = self.request.user.is_superuser or codes & {
            UserProfile.StakeholderType.GOVERNANCE,
            UserProfile.StakeholderType.FOUNDATION_ADMIN,
        }
        program_rows = []
        if ctx["show_programs_section"]:
            from apps.programs.models import Program
            from apps.programs.visibility import filter_programs_for_user
            progs = filter_programs_for_user(Program.objects.all(), self.request.user).prefetch_related('milestones', 'projects')
            for prog in progs:
                milestones = list(prog.milestones.all())
                total_ms = len(milestones)
                completed_ms = sum(1 for m in milestones if m.completed)
                progress = int((completed_ms / total_ms) * 100) if total_ms > 0 else 0
                program_rows.append({
                    "program": prog,
                    "progress_pct": progress,
                    "milestones_total": total_ms,
                    "milestones_completed": completed_ms,
                    "incubator_projects": prog.projects.all()
                })
        ctx["program_rows"] = program_rows
        return ctx


class GovernanceQueueView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/governance_queue.html"

    def dispatch(self, request, *args, **kwargs):
        if not (
            request.user.is_superuser
            or has_stakeholder_type(
                request.user,
                UserProfile.StakeholderType.GOVERNANCE,
                UserProfile.StakeholderType.FOUNDATION_ADMIN,
            )
        ):
            return redirect("dashboard:home")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["needs_gov"] = Need.objects.filter(status=Need.Status.PENDING_GOVERNANCE).prefetch_related(
            "owners"
        )
        ctx["projects_gov"] = Project.objects.filter(
            status=Project.Status.PENDING_GOVERNANCE
        ).prefetch_related("owners")
        ctx["expenses_gov"] = (
            Expense.objects.select_related("project", "requested_by")
            .filter(status=Expense.Status.PENDING_GOVERNANCE)
            .prefetch_related("owners")
        )
        rq = (self.request.GET.get("q") or "").strip()
        ctx["roster_q"] = rq
        ctx["persona_cards"] = roster.persona_cards(rq)
        ctx["roster_search_hits"] = roster.unified_search_hits(rq)
        ctx["roster_lead_cap"] = roster.MAX_LEADS_FOR_AVAILABLE
        ctx["roster_volunteer_cap"] = roster.MAX_VOLUNTEER_TEAMS_FOR_AVAILABLE
        ctx["milestones_funding_gov"] = milestones_awaiting_funding_release()
        ctx["users_needing_persona"] = roster.users_needing_persona_assignment(rq)
        ctx["bulk_profile_form"] = GovernanceProfileBulkForm()
        ctx["csv_preview"] = self.request.session.pop("csv_import_preview", None)
        from apps.stakeholders.models import UserRoleRequest

        pending = UserRoleRequest.objects.filter(status=UserRoleRequest.Status.PENDING).select_related(
            "user"
        )
        ctx["pending_role_requests"] = pending
        ctx["pending_role_request_count"] = pending.count()
        return ctx


class GovernanceProfileBulkForm(forms.Form):
    csv_file = forms.FileField(
        label="CSV file",
        help_text="UTF-8. Required columns: username, email. Optional: first_name, last_name, personas, organization, jurisdiction.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["csv_file"].widget.attrs.update(
            {
                "class": "block w-full cursor-pointer rounded-lg border border-slate-300 bg-white text-sm text-slate-700 file:mr-3 file:rounded file:border-0 file:bg-emerald-100 file:px-3 file:py-2 file:text-sm file:font-medium file:text-emerald-900",
            }
        )


def governance_profile_bulk_upload(request):
    if not request.user.is_authenticated:
        return auth_redirect_login(request.get_full_path())
    if not (
        request.user.is_superuser
        or has_stakeholder_type(
            request.user,
            UserProfile.StakeholderType.GOVERNANCE,
            UserProfile.StakeholderType.FOUNDATION_ADMIN,
        )
    ):
        messages.error(request, "Not allowed.")
        return redirect("dashboard:home")
    if request.method != "POST":
        return redirect("dashboard:governance_queue")
    form = GovernanceProfileBulkForm(request.POST, request.FILES)
    if not form.is_valid():
        for err in form.errors.get("csv_file", ["Invalid upload."]):
            messages.error(request, err)
        return redirect("dashboard:governance_queue")
    
    csv_file = form.cleaned_data["csv_file"]
    from apps.core.upload_security import process_upload
    from django.core.exceptions import ValidationError
    try:
        process_upload(csv_file, request.user, "csv_import", allowed_mimes=["text/csv", "application/csv", "application/vnd.ms-excel", "text/plain"])
    except ValidationError as e:
        messages.error(request, str(e.message) if hasattr(e, 'message') else str(e))
        return redirect("dashboard:governance_queue")

    rows, err = parse_profile_upload_csv(csv_file)
    if err:
        messages.error(request, err)
        return redirect("dashboard:governance_queue")
    preview = _build_csv_preview(rows)
    request.session["csv_import_preview"] = preview
    request.session["csv_import_rows"] = rows
    if preview["error_count"]:
        messages.warning(
            request,
            f"CSV parsed: {preview['valid_count']} valid, {preview['flagged_count']} flagged, "
            f"{preview['error_count']} error(s). Review before confirming.",
        )
    else:
        messages.info(
            request,
            f"CSV ready: {preview['valid_count']} valid row(s), {preview['flagged_count']} flagged. Confirm to import.",
        )
    return redirect("dashboard:governance_queue")


def governance_csv_confirm(request):
    if not request.user.is_authenticated:
        return auth_redirect_login(request.get_full_path())
    if not (
        request.user.is_superuser
        or has_stakeholder_type(
            request.user,
            UserProfile.StakeholderType.GOVERNANCE,
            UserProfile.StakeholderType.FOUNDATION_ADMIN,
        )
    ):
        messages.error(request, "Not allowed.")
        return redirect("dashboard:home")
    if request.method != "POST":
        return redirect("dashboard:governance_queue")
    rows = request.session.pop("csv_import_rows", None)
    request.session.pop("csv_import_preview", None)
    if not rows:
        messages.error(request, "No import in progress. Upload a CSV again.")
        return redirect("dashboard:governance_queue")
    result = apply_profile_bulk_rows(rows)
    for w in result["warnings"]:
        messages.warning(request, w)
    for e in result["errors"]:
        messages.error(request, e)
    if result["created"] or result["updated"]:
        messages.success(
            request,
            f"Import finished: {result['created']} user(s) created, {result['updated']} updated.",
        )
    elif not result["errors"]:
        messages.info(request, "No rows processed.")
    return redirect("dashboard:governance_queue")


def _build_csv_preview(rows: list[dict]) -> dict:
    from apps.stakeholders.persona_utils import parse_persona_cell, _norm_jurisdiction
    from django.core.validators import validate_email
    from django.core.exceptions import ValidationError
    from django.contrib.auth import get_user_model
    User = get_user_model()

    flagged = []
    errors = []
    valid_count = 0
    for i, row in enumerate(rows, start=1):
        username = (row.get("username") or "").strip()
        email = (row.get("email") or "").strip()
        if not username or not email:
            errors.append({"row": i, "username": username or "—", "reason": "Missing username or email"})
            continue
            
        try:
            validate_email(email)
        except ValidationError:
            errors.append({"row": i, "username": username, "reason": "Invalid email format"})
            continue

        existing_user = User.objects.filter(username__iexact=username).first()
        if existing_user and existing_user.email.lower() != email.lower():
             errors.append({"row": i, "username": username, "reason": "Username exists with different email"})
             continue

        email_taken = User.objects.filter(email__iexact=email).exclude(username__iexact=username).exists()
        if email_taken:
             errors.append({"row": i, "username": username, "reason": "Email already used by another username"})
             continue

        personas_raw = row.get("personas") or ""
        valid_p, unknown = parse_persona_cell(personas_raw)
        if unknown:
            flagged.append(
                {"row": i, "username": username, "reason": f"Unknown persona token(s): {', '.join(unknown)}"}
            )
        elif not valid_p and not personas_raw.strip():
            flagged.append({"row": i, "username": username, "reason": "No personas — will need assignment"})
        else:
            valid_count += 1
            
        jur = row.get("jurisdiction")
        if jur and _norm_jurisdiction(jur) == "india" and jur.strip().lower() != "india":
            # Just an example check, _norm_jurisdiction falls back to INDIA
            pass

    return {
        "valid_count": valid_count,
        "flagged_count": len(flagged),
        "error_count": len(errors),
        "flagged_rows": flagged[:50],
        "error_rows": errors[:50],
        "total_rows": len(rows),
    }


def switch_role(request):
    if request.method != "POST" or not request.user.is_authenticated:
        return redirect("dashboard:home")
    persona = (request.POST.get("persona") or "").strip()
    codes = user_stakeholder_codes(request.user)
    if request.user.is_superuser:
        codes = codes | {UserProfile.StakeholderType.FOUNDATION_ADMIN}
    if persona in codes:
        request.session["active_persona"] = persona
        messages.success(request, "Active role updated.")
    return redirect("dashboard:home")


def toggle_currency(request):
    if request.method != "POST" or not request.user.is_authenticated:
        return redirect("dashboard:home")
    current = request.session.get("display_currency", "USD")
    request.session["display_currency"] = "INR" if current == "USD" else "USD"
    return redirect("dashboard:home")



def governance_profile_sample_csv(request):
    if not request.user.is_authenticated:
        return auth_redirect_login(request.get_full_path())
    if not (
        request.user.is_superuser
        or has_stakeholder_type(
            request.user,
            UserProfile.StakeholderType.GOVERNANCE,
            UserProfile.StakeholderType.FOUNDATION_ADMIN,
        )
    ):
        messages.error(request, "Not allowed.")
        return redirect("dashboard:home")
    resp = HttpResponse(sample_csv_text(), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = 'attachment; filename="profile_import_sample.csv"'
    return resp
