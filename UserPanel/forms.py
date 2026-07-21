from django import forms

from .models import UserTicket

class TicketForm(forms.ModelForm):
    class Meta:
        model = UserTicket
        fields = [
            'title',
            'priority',
            'department',
            'start_date',
            'message',
        ]

        # استایل دهی با Bootstrap
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter ticket title'
            }),
            'priority': forms.Select(attrs={'class': 'form-select'}),
            'department': forms.Select(attrs={'class': 'form-select'}),
            'start_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'message': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Enter your message'
            }),
        }

        labels = {
            'title': 'Ticket Title *',
            'priority': 'Priority *',
            'department': 'Department *',
            'start_date': 'Start Date *',
            'message': 'Message *',
        }

