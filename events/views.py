from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from .models import EventPoster, EventRegistration
from .forms import EventRegistrationForm


def events_home(request):
    event = EventPoster.objects.filter(is_active=True).order_by("-created_at").first()
    return render(request, "events/home.html", {"event": event})


def event_register(request, event_id):
    event = get_object_or_404(EventPoster, id=event_id, is_active=True)

    if request.method == "POST":
        form = EventRegistrationForm(request.POST)
        if form.is_valid():
            registration = form.save(commit=False)
            registration.event = event
            registration.save()
            return redirect("event_success")
    else:
        form = EventRegistrationForm()

    return render(request, "events/register.html", {
        "event": event,
        "form": form,
    })


def event_success(request):
    return render(request, "events/success.html")


def is_church_user(user):
    return user.is_authenticated and (user.is_staff or user.groups.filter(name="Church Users").exists())


@login_required
@user_passes_test(is_church_user)
def event_submissions(request, event_id):
    event = get_object_or_404(EventPoster, id=event_id)
    submissions = event.registrations.all().order_by("-submitted_at")

    return render(request, "events/submissions.html", {
        "event": event,
        "submissions": submissions,
    })