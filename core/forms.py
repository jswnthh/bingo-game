import re

from django import forms

from .models import Room

FIELD_CLASS = "field-input"


class CreateRoomForm(forms.Form):
    title = forms.CharField(
        label="Room / subject name",
        max_length=200,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Operating Systems",
                "autocomplete": "off",
                "class": FIELD_CLASS,
            }
        ),
    )
    phrases = forms.CharField(
        label="Professor phrases",
        widget=forms.Textarea(
            attrs={
                "rows": 12,
                "placeholder": "Am I clear?\nThis is very important\nAny doubts?\n…",
                "class": FIELD_CLASS,
            }
        ),
        help_text="One phrase per line. At least 24 unique phrases.",
    )

    def clean_title(self):
        title = self.cleaned_data["title"].strip()
        if not title:
            raise forms.ValidationError("Please enter a room name.")
        return title

    def clean_phrases(self):
        raw = self.cleaned_data["phrases"]
        lines = [line.strip() for line in raw.splitlines()]
        phrases = []
        seen = set()
        for line in lines:
            if not line:
                continue
            key = line.casefold()
            if key in seen:
                continue
            seen.add(key)
            phrases.append(line)
        if len(phrases) < 24:
            raise forms.ValidationError(
                f"Add at least 24 unique phrases (you have {len(phrases)})."
            )
        return phrases


class JoinRoomForm(forms.Form):
    code = forms.CharField(
        label="Room code",
        max_length=6,
        widget=forms.TextInput(
            attrs={
                "placeholder": "ENTER ROOM CODE",
                "autocomplete": "off",
                "class": FIELD_CLASS,
                "maxlength": "6",
            }
        ),
    )

    def clean_code(self):
        code = self.cleaned_data["code"].strip().upper()
        code = re.sub(r"[^A-Z0-9]", "", code)
        if len(code) != 6:
            raise forms.ValidationError("Enter a 6-character room code.")
        try:
            room = Room.objects.get(code=code)
        except Room.DoesNotExist:
            raise forms.ValidationError(
                "We couldn't find a room with that code. Check it and try again."
            )
        self.cleaned_data["room"] = room
        return code


class NicknameForm(forms.Form):
    nickname = forms.CharField(
        label="Your nickname",
        max_length=50,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Student 42",
                "autocomplete": "nickname",
                "class": FIELD_CLASS,
            }
        ),
    )

    def clean_nickname(self):
        nickname = self.cleaned_data["nickname"].strip()
        if not nickname:
            raise forms.ValidationError("Please enter a nickname.")
        return nickname
