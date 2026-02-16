from django.http import HttpResponse
from django.shortcuts import render, redirect
from .forms import DoctorRegisterForm, PharmacistRegisterForm
from django.contrib.auth.decorators import login_required

def doctor_register(request):
    if request.method == 'POST':
        form = DoctorRegisterForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return redirect('login')
        else:
            print(form.errors)  # 👈 ADD THIS
    else:
        form = DoctorRegisterForm()

    return render(request, 'accounts/register.html', {'form': form, 'role': 'Doctor'})


def pharmacist_register(request):
    if request.method == 'POST':
        form = PharmacistRegisterForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return redirect('login')
    else:
        form = PharmacistRegisterForm()

    return render(request, 'accounts/register.html', {'form': form, 'role': 'Pharmacist'})

@login_required
def role_redirect(request):
    user = request.user

    if not user.is_approved:
        return redirect('pending')

    if user.role == 'ADMIN':
        return redirect('/admin/')

    elif user.role == 'DOCTOR':
        return redirect('doctor_dashboard')

    elif user.role == 'PHARMACIST':
        return redirect('pharmacist_dashboard')

    return redirect('login')

@login_required
def pending_view(request):
    return render(request, 'accounts/pending.html')

@login_required
def doctor_dashboard(request):
    if request.user.role != 'DOCTOR':
        return redirect('login')

    if not request.user.is_approved:
        return redirect('pending')

    context = {
        "user": request.user,
    }
    return render(request, "accounts/doctor_dashboard.html", context)


@login_required
def pharmacist_dashboard(request):
    if request.user.role != 'PHARMACIST':
        return redirect('login')

    if not request.user.is_approved:
        return redirect('pending')

    context = {
        "user": request.user,
    }
    return render(request, "accounts/pharmacist_dashboard.html", context)
