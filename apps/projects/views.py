from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import ValidationError
from django.db.models import Max, Prefetch
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.core.permissions import has_stakeholder_type, user_stakeholder_codes
from apps.core.thresholds import project_requires_governance
from apps.needs.models import Need
from apps.needs.visibility import (
    can_create_project,
    can_initiate_project_creation,
    can_manage_milestones,
    can_release_milestone_funding,
    filter_needs_for_user,
    filter_projects_for_user,
)
from apps.funding.visibility import can_manage_expense, can_record_contribution
from apps.projects.attachments import save_project_attachments, validate_project_attachment_files
from apps.projects.forms import MilestoneForm, ProjectForm
from apps.projects.models import Milestone, Project, ProjectAttachment
from apps.projects.progress import calculate_project_progress
from apps.projects.state_machine import allowed_milestone_next, allowed_project_next
from apps.projects.timeline import timeline_rows
from apps.projects.funding_gates import project_funding_gate_metrics
from apps.stakeholders.models import UserProfile


class ProjectListView(LoginRequiredMixin, ListView):
    model = Project
    template_name = "projects/project_list.html"
    context_object_name = "projects"

    def get_queryset(self):
        return filter_projects_for_user(
            Project.objects.select_related("need", "lead").prefetch_related("owners"), self.request.user
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["can_add_project"] = can_initiate_project_creation(self.request.user)
        return ctx


class ProjectDetailView(LoginRequiredMixin, DetailView):
    model = Project
    template_name = "projects/project_detail.html"
    context_object_name = "project"

    def get_queryset(self):
        return filter_projects_for_user(
            Project.objects.select_related("need", "lead").prefetch_related(
                "attachments__uploaded_by",
                "owners",
                Prefetch(
                    "milestones",
                    queryset=Milestone.objects.select_related("assigned_to")
                    .prefetch_related("owners")
                    .order_by("sequence", "id"),
                ),
            ),
            self.request.user,
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["progress_pct"] = calculate_project_progress(self.object)
        milestones = list(self.object.milestones.all())
        ctx["timeline"] = timeline_rows(self.object, milestones=milestones)
        ctx["allowed_project_next"] = allowed_project_next(self.object.status)
        ctx["can_manage_milestones"] = can_manage_milestones(self.request.user, self.object)
        u = self.request.user
        ctx["can_transition_project"] = u.is_superuser or has_stakeholder_type(
            u, UserProfile.StakeholderType.FOUNDATION_ADMIN
        ) or (
            has_stakeholder_type(u, UserProfile.StakeholderType.GOVERNANCE)
            and self.object.status == Project.Status.PENDING_GOVERNANCE
        )
        ctx["can_prefill_contribution"] = can_record_contribution(self.request.user)
        ctx["can_prefill_expense"] = can_manage_expense(self.request.user)
        ctx["funding_gate_metrics"] = project_funding_gate_metrics(self.object)
        ctx["can_release_milestone_funding"] = can_release_milestone_funding(self.request.user)
        return ctx


class ProjectCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = Project
    form_class = ProjectForm
    template_name = "projects/project_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.need = get_object_or_404(
            filter_needs_for_user(Need.objects.prefetch_related("owners"), request.user),
            pk=kwargs["need_id"],
        )
        return super().dispatch(request, *args, **kwargs)

    def test_func(self):
        return can_create_project(self.request.user, self.need)

    def get_initial(self):
        initial = super().get_initial()
        n = self.need
        initial["title"] = n.title
        if n.description:
            initial["description"] = n.description
        initial["budget"] = n.target_amount
        initial["budget_currency"] = n.target_currency or "INR"
        if n.funding_model == Need.FundingModel.ANCHOR:
            initial["funding_model"] = Project.FundingModel.ANCHOR
        elif n.funding_model == Need.FundingModel.POOLED:
            initial["funding_model"] = Project.FundingModel.POOLED
        else:
            initial["funding_model"] = Project.FundingModel.INHERITED
        if UserProfile.StakeholderType.PROJECT_LEAD in user_stakeholder_codes(self.request.user):
            initial["lead"] = self.request.user.pk
        oids = list(n.owners.values_list("pk", flat=True))
        initial["owners"] = oids or [self.request.user.pk]
        return initial

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["need"] = self.need
        return kw

    def form_valid(self, form):
        files = self.request.FILES.getlist("attachments")
        try:
            validate_project_attachment_files(files)
        except ValidationError as e:
            form.add_error(None, e)
            return self.form_invalid(form)
        form.instance.need = self.need
        form.instance.status = Project.Status.PROPOSED
        if project_requires_governance(form.instance.budget, form.instance.budget_currency):
            form.instance.status = Project.Status.PENDING_GOVERNANCE
            gov_msg = True
        else:
            gov_msg = False
        response = super().form_valid(form)
        n = save_project_attachments(self.object, files, self.request.user)
        if n:
            messages.info(self.request, f"Uploaded {n} attachment(s).")
        if gov_msg:
            messages.info(self.request, "Project routed to governance (budget over threshold).")
        else:
            messages.success(self.request, "Project created.")
        return response

    def get_success_url(self):
        return reverse("projects:detail", kwargs={"pk": self.object.pk})


class ProjectUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Project
    form_class = ProjectForm
    template_name = "projects/project_form.html"

    def get_queryset(self):
        return filter_projects_for_user(
            Project.objects.prefetch_related("attachments", "owners"), self.request.user
        )

    def test_func(self):
        u = self.request.user
        p = self.get_object()
        if u.is_superuser or has_stakeholder_type(u, UserProfile.StakeholderType.FOUNDATION_ADMIN):
            return True
        return has_stakeholder_type(u, UserProfile.StakeholderType.PROJECT_LEAD) and p.lead_id == u.id

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["need"] = self.object.need
        return kw

    def form_valid(self, form):
        files = self.request.FILES.getlist("attachments")
        try:
            validate_project_attachment_files(files)
        except ValidationError as e:
            form.add_error(None, e)
            return self.form_invalid(form)
        response = super().form_valid(form)
        n = save_project_attachments(self.object, files, self.request.user)
        if n:
            messages.success(self.request, f"Project updated; added {n} attachment(s).")
        else:
            messages.success(self.request, "Project updated.")
        return response

    def get_success_url(self):
        return reverse("projects:detail", kwargs={"pk": self.object.pk})


def project_transition(request, pk):
    project = get_object_or_404(filter_projects_for_user(Project.objects.all(), request.user), pk=pk)
    if not (
        request.user.is_superuser
        or has_stakeholder_type(request.user, UserProfile.StakeholderType.FOUNDATION_ADMIN)
    ):
        if not (
            has_stakeholder_type(request.user, UserProfile.StakeholderType.GOVERNANCE)
            and project.status == "pending_governance"
        ):
            messages.error(request, "Not allowed.")
            return redirect("projects:detail", pk=pk)
    if request.method != "POST":
        return redirect("projects:detail", pk=pk)
    nxt = request.POST.get("next_status")
    if nxt not in allowed_project_next(project.status):
        messages.error(request, "Invalid transition.")
        return redirect("projects:detail", pk=pk)
    project.status = nxt
    project.save()
    messages.success(request, "Project status updated.")
    return redirect("projects:detail", pk=pk)


class MilestoneCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = Milestone
    form_class = MilestoneForm
    template_name = "projects/milestone_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.project = get_object_or_404(
            filter_projects_for_user(Project.objects.prefetch_related("owners"), request.user),
            pk=kwargs["project_id"],
        )
        return super().dispatch(request, *args, **kwargs)

    def test_func(self):
        return can_manage_milestones(self.request.user, self.project)

    def get_initial(self):
        initial = super().get_initial()
        p = self.project
        mx = p.milestones.aggregate(v=Max("sequence"))["v"]
        initial["sequence"] = (mx if mx is not None else -1) + 1
        if p.lead_id:
            initial["assigned_to"] = p.lead_id
        last = p.milestones.order_by("-sequence", "-id").first()
        if last:
            sd = last.due_date + timedelta(days=1)
            initial["start_date"] = sd
            initial["due_date"] = sd + timedelta(days=30)
        elif p.start_date:
            initial["start_date"] = p.start_date
            initial["due_date"] = p.target_end_date or p.start_date
        else:
            today = date.today()
            initial["start_date"] = today
            initial["due_date"] = today + timedelta(days=30)
        oids = list(p.owners.values_list("pk", flat=True))
        if not oids and p.lead_id:
            oids = [p.lead_id]
        if not oids:
            oids = [self.request.user.pk]
        initial["owners"] = oids
        return initial

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["project"] = self.project
        kw["user"] = self.request.user
        return kw

    def form_valid(self, form):
        form.instance.project = self.project
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("projects:detail", kwargs={"pk": self.project.pk})


class MilestoneUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Milestone
    form_class = MilestoneForm
    template_name = "projects/milestone_form.html"

    def get_queryset(self):
        pqs = filter_projects_for_user(Project.objects.all(), self.request.user)
        return Milestone.objects.filter(project__in=pqs).prefetch_related("owners")

    def test_func(self):
        return can_manage_milestones(self.request.user, self.get_object().project)

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["project"] = self.get_object().project
        kw["user"] = self.request.user
        return kw

    def get_success_url(self):
        return reverse("projects:detail", kwargs={"pk": self.object.project_id})


def milestone_transition(request, pk):
    ms = get_object_or_404(
        Milestone.objects.select_related("project"),
        pk=pk,
    )
    if not can_manage_milestones(request.user, ms.project):
        messages.error(request, "Not allowed.")
        return redirect("projects:detail", pk=ms.project_id)
    if request.method != "POST":
        return redirect("projects:detail", pk=ms.project_id)
    nxt = request.POST.get("next_status")
    if nxt not in allowed_milestone_next(ms.status):
        messages.error(request, "Invalid transition.")
        return redirect("projects:detail", pk=ms.project_id)
    if nxt == Milestone.Status.DONE:
        tr_pct = ms.next_tranche_budget_percent or 0
        if tr_pct > 0 and not ms.completion_proof:
            messages.error(
                request,
                "Upload a completion proof document on Edit milestone before marking done (funding tranche is set).",
            )
            return redirect("projects:detail", pk=ms.project_id)
    ms.status = nxt
    if nxt == Milestone.Status.DONE and not ms.completed_date:
        ms.completed_date = date.today()
        tr_pct = ms.next_tranche_budget_percent or 0
        if tr_pct > 0:
            ms.tranche_governance_status = Milestone.TrancheGovernance.AWAITING_GOVERNANCE
        else:
            ms.tranche_governance_status = Milestone.TrancheGovernance.NOT_APPLICABLE
    ms.save()
    messages.success(request, "Milestone updated.")
    return redirect("projects:detail", pk=ms.project_id)


def milestone_proof_download(request, pk):
    ms = get_object_or_404(Milestone.objects.select_related("project"), pk=pk)
    get_object_or_404(filter_projects_for_user(Project.objects.filter(pk=ms.project_id), request.user))
    if not ms.completion_proof:
        raise Http404()
    try:
        fh = ms.completion_proof.open("rb")
    except FileNotFoundError:
        raise Http404()
    return FileResponse(
        fh,
        as_attachment=True,
        filename=ms.completion_proof_original_filename or ms.completion_proof.name.rsplit("/", 1)[-1],
    )


def milestone_tranche_release(request, pk):
    ms = get_object_or_404(Milestone.objects.select_related("project"), pk=pk)
    get_object_or_404(filter_projects_for_user(Project.objects.filter(pk=ms.project_id), request.user))
    if not can_release_milestone_funding(request.user):
        messages.error(request, "Not allowed.")
        return redirect("projects:detail", pk=ms.project_id)
    if request.method != "POST":
        return redirect("projects:detail", pk=ms.project_id)
    if ms.tranche_governance_status != Milestone.TrancheGovernance.AWAITING_GOVERNANCE:
        messages.error(request, "This milestone is not awaiting a funding release.")
        return redirect("projects:detail", pk=ms.project_id)
    action = request.POST.get("action")
    if action == "release":
        if not ms.completion_proof:
            messages.error(request, "Proof document is missing.")
            return redirect("projects:detail", pk=ms.project_id)
        ms.tranche_governance_status = Milestone.TrancheGovernance.RELEASED
        ms.save(update_fields=["tranche_governance_status"])
        messages.success(request, "Funding tranche released for this milestone.")
    elif action == "reject":
        ms.tranche_governance_status = Milestone.TrancheGovernance.REJECTED
        ms.save(update_fields=["tranche_governance_status"])
        messages.warning(request, "Funding tranche marked rejected. Coordinate with the project lead.")
    else:
        messages.error(request, "Invalid action.")
    return redirect("projects:detail", pk=ms.project_id)


def project_timeline_partial(request, pk):
    project = get_object_or_404(filter_projects_for_user(Project.objects.all(), request.user), pk=pk)
    return render(
        request,
        "projects/partials/timeline.html",
        {"project": project, "timeline": timeline_rows(project)},
    )


def project_attachment_download(request, pk, attachment_pk):
    project = get_object_or_404(filter_projects_for_user(Project.objects.all(), request.user), pk=pk)
    att = get_object_or_404(ProjectAttachment.objects.filter(project=project), pk=attachment_pk)
    if not att.file:
        raise Http404()
    try:
        fh = att.file.open("rb")
    except FileNotFoundError:
        raise Http404()
    return FileResponse(
        fh,
        as_attachment=True,
        filename=att.original_filename or att.file.name.rsplit("/", 1)[-1],
    )
