from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q

from apps.core.owner_fields import OWNERS_SELECT_ATTRS, active_registered_users_queryset
from apps.core.thresholds import expense_requires_governance
from apps.events.models import Event
from apps.funding.models import Contribution, Expense, FundPool
from apps.stakeholders.models import UserProfile

User = get_user_model()


class ContributionForm(forms.ModelForm):
    class Meta:
        model = Contribution
        fields = [
            "donor",
            "project",
            "event",
            "fund_pool",
            "amount",
            "currency",
            "jurisdiction_origin",
            "status",
            "pledge_date",
            "received_date",
            "receipt_sent",
            "receipt_sent_date",
            "communication_capture_url",
            "volunteer_lead",
            "reference_number",
            "notes",
        ]
        labels = {
            "receipt_sent": "Receipt sent",
            "receipt_sent_date": "Receipt sent date",
            "communication_capture_url": "Communication capture (S3 / file URL)",
            "volunteer_lead": "Volunteer lead (HNI stewardship)",
        }

    def __init__(self, *args, **kwargs):
        self._user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        donor_q = Q(profile__stakeholder_type=UserProfile.StakeholderType.DONOR) | Q(
            stakeholder_personas__persona_type=UserProfile.StakeholderType.DONOR
        )
        donors = self.fields["donor"].queryset.model.objects.filter(donor_q, is_active=True).distinct()
        if donors.exists():
            self.fields["donor"].queryset = donors
        else:
            self.fields["donor"].queryset = self.fields["donor"].queryset.model.objects.filter(
                is_active=True
            ).order_by("username")
        lead_q = Q(profile__stakeholder_type=UserProfile.StakeholderType.VOLUNTEER) | Q(
            stakeholder_personas__persona_type=UserProfile.StakeholderType.VOLUNTEER
        ) | Q(profile__stakeholder_type=UserProfile.StakeholderType.PROJECT_LEAD) | Q(
            stakeholder_personas__persona_type=UserProfile.StakeholderType.PROJECT_LEAD
        )
        leads = User.objects.filter(lead_q, is_active=True).distinct().order_by("username")
        self.fields["volunteer_lead"].queryset = leads
        self.fields["volunteer_lead"].required = False
        self.fields["project"].required = False
        self.fields["event"].required = False
        self.fields["event"].queryset = Event.objects.filter(
            status__in=[
                Event.Status.PUBLISHED,
                Event.Status.REGISTRATION_OPEN,
                Event.Status.ONGOING,
                Event.Status.COMPLETED,
            ]
        ).order_by("-start_datetime")

        # Friendly select placeholders
        self.fields["donor"].empty_label = "Choose Donor..."
        self.fields["project"].empty_label = "Choose Project (Optional)..."
        self.fields["event"].empty_label = "Choose Event (Optional)..."
        self.fields["fund_pool"].empty_label = "Choose Fund Pool..."
        self.fields["volunteer_lead"].empty_label = "Choose Volunteer Lead (Optional)..."
        self.fields["jurisdiction_origin"].choices = [("", "Choose Jurisdiction...")] + [c for c in self.fields["jurisdiction_origin"].choices if c[0] != ""]

        # Visual calendar pickers
        self.fields["pledge_date"].widget = forms.DateInput(attrs={"type": "date"})
        self.fields["received_date"].widget = forms.DateInput(attrs={"type": "date"})
        self.fields["receipt_sent_date"].widget = forms.DateInput(attrs={"type": "date"})


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = [
            "project",
            "fund_pool",
            "amount",
            "currency",
            "description",
            "expense_date",
            "receipt_reference",
            "owners",
            "receipt_pdf",
        ]

    def __init__(self, *args, **kwargs):
        self._user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self.fields["owners"].queryset = active_registered_users_queryset()
        self.fields["owners"].label = "Owners (approval / accountability)"
        self.fields["owners"].help_text = "At least one registered user (e.g. you as requester; add finance if needed)."
        self.fields["owners"].widget.attrs.update(OWNERS_SELECT_ATTRS)

        # Friendly select placeholders
        self.fields["project"].empty_label = "Choose Project..."
        self.fields["fund_pool"].empty_label = "Choose Fund Pool..."

        # Visual calendar picker
        self.fields["expense_date"].widget = forms.DateInput(attrs={"type": "date"})

        self.fields["receipt_pdf"].label = "Upload Expense Report / Supporting document"
        self.fields["receipt_pdf"].required = False



    def clean_owners(self):
        owners = self.cleaned_data.get("owners")
        if not owners:
            raise forms.ValidationError("Select at least one owner from registered users.")
        return owners

    def save(self, commit=True):
        obj = super().save(commit=False)
        if self._user:
            obj.requested_by = self._user
        obj.requires_governance_approval = expense_requires_governance(obj.amount, obj.currency)
        if obj.requires_governance_approval:
            obj.status = Expense.Status.PENDING_GOVERNANCE
        if commit:
            obj.save()
            self.save_m2m()
        return obj
