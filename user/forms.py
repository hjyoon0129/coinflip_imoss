from django import forms

from .models import UserProfile


class NicknameForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ["nickname"]

    def clean_nickname(self):
        nickname = (self.cleaned_data.get("nickname") or "").strip()

        if not nickname:
            raise forms.ValidationError("Please enter a nickname.")

        if len(nickname) < 2:
            raise forms.ValidationError("Nickname must be at least 2 characters.")

        if len(nickname) > 30:
            raise forms.ValidationError("Nickname must be 30 characters or less.")

        qs = UserProfile.objects.filter(nickname__iexact=nickname)

        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise forms.ValidationError("This nickname is already taken. Please choose another one.")

        return nickname