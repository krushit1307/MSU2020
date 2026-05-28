from django import forms

from apps.events.models import Event, EventMilestone
from apps.funding.models import FundPool
from apps.needs.visibility import filter_needs_for_user, filter_projects_for_user
from apps.projects.models import Project
from apps.needs.models import Need

_INPUT = "mt-1 block w-full rounded border border-slate-300 px-3 py-2 text-sm"
_DT = "mt-1 block w-full rounded border border-slate-300 px-3 py-2 text-sm"


class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = [
            "title",
            "description",
            "event_type",
            "venue",
            "location",
            "virtual_link",
            "start_datetime",
            "end_datetime",
            "jurisdiction",
            "status",
            "linked_project",
            "linked_need",
            "target_amount",
            "fund_pool",
            "target_audience",
            "is_fundraising",
            "details_doc",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": _INPUT}),
            "description": forms.Textarea(attrs={"class": _INPUT, "rows": 5}),
            "venue": forms.TextInput(attrs={"class": _INPUT}),
            "location": forms.TextInput(attrs={"class": _INPUT}),
            "virtual_link": forms.URLInput(attrs={"class": _INPUT}),
            "start_datetime": forms.DateTimeInput(attrs={"class": _DT, "type": "datetime-local"}),
            "end_datetime": forms.DateTimeInput(attrs={"class": _DT, "type": "datetime-local"}),
            "target_amount": forms.NumberInput(attrs={"class": _INPUT}),
            "target_audience": forms.Textarea(attrs={"class": _INPUT, "rows": 2}),
            "is_fundraising": forms.CheckboxInput(attrs={"class": "rounded border-slate-300"}),
            "details_doc": forms.FileInput(attrs={"class": "mt-1 block w-full text-sm text-slate-600 file:mr-3 file:rounded file:border-0 file:bg-emerald-50 file:px-3 file:py-2 file:text-sm file:font-medium file:text-emerald-800 hover:file:bg-emerald-100"}),
        }

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["linked_project"].queryset = filter_projects_for_user(
            Project.objects.all(), user
        )
        self.fields["linked_need"].queryset = filter_needs_for_user(Need.objects.all(), user)
        self.fields["fund_pool"].queryset = FundPool.objects.all()
        for name in ("event_type", "jurisdiction", "status", "linked_project", "linked_need", "fund_pool"):
            if name in self.fields:
                self.fields[name].widget.attrs["class"] = _INPUT
        
        # Friendly select placeholders
        self.fields["linked_project"].empty_label = "Choose Linked Project (Optional)..."
        self.fields["linked_need"].empty_label = "Choose Linked Need (Optional)..."
        self.fields["fund_pool"].empty_label = "Choose Fund Pool (Optional)..."

        self.fields["details_doc"].label = "Upload Event Details / Supporting document"
        self.fields["details_doc"].required = False

        if not self.instance.pk:
            self.fields["status"].initial = Event.Status.DRAFT
            self.fields["status"].widget = forms.HiddenInput()

    def save(self, commit=True):
        inst = super().save(commit=False)
        if not inst.pk:
            inst.organized_by = self.user
            if inst.event_type == Event.EventType.FUNDRAISING or inst.is_fundraising:
                inst.is_fundraising = True
                inst.status = Event.Status.DRAFT
        if commit:
            inst.save()
            self.save_m2m()
        return inst


class EventMilestoneForm(forms.ModelForm):
    class Meta:
        model = EventMilestone
        fields = ["title", "owner", "due_date", "notes", "sequence"]
        widgets = {
            "title": forms.TextInput(attrs={"class": _INPUT}),
            "due_date": forms.DateInput(attrs={"class": _INPUT, "type": "date"}),
            "notes": forms.Textarea(attrs={"class": _INPUT, "rows": 3}),
            "sequence": forms.NumberInput(attrs={"class": _INPUT}),
        }

    def __init__(self, event, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.event = event
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.fields["owner"].queryset = User.objects.filter(is_active=True).order_by("username")
        self.fields["owner"].widget.attrs["class"] = _INPUT
