from django import forms

from apps.core.owner_fields import OWNERS_SELECT_ATTRS, active_registered_users_queryset
from apps.core.thresholds import need_requires_governance
from apps.needs.models import Need


class NeedForm(forms.ModelForm):
    class Meta:
        model = Need
        fields = [
            "title",
            "description",
            "department",
            "funding_model",
            "jurisdiction",
            "scope",
            "target_amount",
            "target_currency",
            "owners",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["owners"].queryset = active_registered_users_queryset()
        self.fields["owners"].label = "Owners"
        self.fields["owners"].help_text = "At least one registered user accountable for this need."
        self.fields["owners"].widget.attrs.update(OWNERS_SELECT_ATTRS)
        
        # If it is a new form, clear out the default 0 value so the field is initially empty
        if not self.instance.pk:
            self.fields["target_amount"].initial = ""
        self.fields["target_amount"].widget.attrs.update({"min": "0"})
        
        # Set empty label for Department field
        self.fields["department"].empty_label = "Choose Department...."

    def clean_target_amount(self):
        amount = self.cleaned_data.get("target_amount")
        if amount is not None and amount <= 0:
            raise forms.ValidationError("Target amount must be a positive number greater than zero.")
        return amount

    def clean_owners(self):
        owners = self.cleaned_data.get("owners")
        if not owners:
            raise forms.ValidationError("Select at least one owner from registered users.")
        return owners

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.requires_governance_approval = need_requires_governance(obj.target_amount, obj.target_currency)
        if commit:
            obj.save()
            self.save_m2m()
        return obj


class NeedMatchForm(forms.Form):
    donor_ids = forms.ModelMultipleChoiceField(
        queryset=None,
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "mt-1 block w-full rounded border p-2", "size": 8}),
        label="Matched donors",
    )

    def __init__(self, *args, **kwargs):
        donor_queryset = kwargs.pop("donor_queryset")
        super().__init__(*args, **kwargs)
        self.fields["donor_ids"].queryset = donor_queryset
