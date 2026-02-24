from django.shortcuts import render, redirect
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
from django.contrib.auth import views as auth_views
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib import messages

from .models import User
from .forms import LoginForm, UserCreateForm, UserUpdateForm, ProfileForm


class AdminRequiredMixin(UserPassesTestMixin):
    """Mixin that requires user to be an admin."""
    
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_admin


class LoginView(auth_views.LoginView):
    """
    Custom login view with enhanced security features.
    
    Features:
    - Remember me functionality (persistent session)
    - Failed login attempt logging
    - IP address tracking for audit
    - Always redirects to dashboard (ignores ?next parameter)
    """
    
    template_name = 'accounts/login.html'
    authentication_form = LoginForm
    redirect_authenticated_user = True
    
    def get_success_url(self):
        """Always redirect to dashboard after login."""
        return reverse_lazy('dashboard')
    
    def form_valid(self, form):
        """Handle successful login with remember me support."""
        response = super().form_valid(form)
        
        # Handle "Remember Me" checkbox
        # Session timeout is capped at SESSION_COOKIE_AGE (1 hour) for security
        remember_me = self.request.POST.get('remember_me')
        if remember_me:
            # Use configured session timeout (1 hour) - persists across browser close
            self.request.session.set_expiry(None)  # Use SESSION_COOKIE_AGE
        else:
            # Session expires when browser closes
            self.request.session.set_expiry(0)
        
        # Log successful login
        try:
            from sabra.activities.models import SystemLog
            ip_address = self.request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or \
                        self.request.META.get('REMOTE_ADDR')
            SystemLog.log(
                'auth', 'success',
                f"User logged in: {self.request.user.username}",
                user=self.request.user,
                ip_address=ip_address,
                source='login'
            )
        except Exception:
            pass
        
        return response
    
    def form_invalid(self, form):
        """Log failed login attempt."""
        response = super().form_invalid(form)
        try:
            from sabra.activities.models import SystemLog
            ip_address = self.request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or \
                        self.request.META.get('REMOTE_ADDR')
            email = form.cleaned_data.get('username', 'unknown')
            SystemLog.log(
                'auth', 'warning',
                f"Failed login attempt for: {email}",
                ip_address=ip_address,
                source='login'
            )
        except Exception:
            pass
        return response


class LogoutView(TemplateView):
    """
    Custom logout view with security best practices.
    
    - GET request: Shows logout confirmation page
    - POST request: Performs actual logout and redirects
    
    Django 5+ requires POST for logout for CSRF protection.
    We implement this manually instead of using auth_views.LogoutView
    to properly support GET for confirmation page.
    """
    
    template_name = 'accounts/logout_confirm.html'
    
    def get(self, request, *args, **kwargs):
        """Show logout confirmation page for GET requests."""
        if not request.user.is_authenticated:
            # Already logged out, redirect to login
            return redirect('accounts:login')
        return super().get(request, *args, **kwargs)
    
    def post(self, request, *args, **kwargs):
        """Perform logout on POST request."""
        from django.contrib.auth import logout
        
        if request.user.is_authenticated:
            user_username = request.user.username
            
            # Log the logout event before clearing session
            try:
                from sabra.activities.models import SystemLog
                ip_address = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or \
                            request.META.get('REMOTE_ADDR')
                SystemLog.log(
                    'auth', 'info',
                    f"User logged out: {user_username}",
                    user=request.user,
                    ip_address=ip_address,
                    source='logout'
                )
            except Exception:
                pass
        
        # Perform the actual logout (clears session)
        logout(request)
        
        return redirect('accounts:logged_out')


class LoggedOutView(TemplateView):
    """
    Displayed after successful logout.
    Uses base_auth.html for clean presentation without app chrome.
    """
    template_name = 'accounts/logged_out.html'


class PasswordChangeView(LoginRequiredMixin, auth_views.PasswordChangeView):
    """Password change view."""
    
    template_name = 'accounts/password_change.html'
    success_url = reverse_lazy('accounts:password_change_done')
    
    def form_valid(self, form):
        """Clear must_change_password flag after successful password change."""
        response = super().form_valid(form)
        # Clear the must_change_password flag
        if hasattr(self.request.user, 'must_change_password') and self.request.user.must_change_password:
            self.request.user.must_change_password = False
            self.request.user.save(update_fields=['must_change_password'])
        return response


class PasswordChangeDoneView(LoginRequiredMixin, auth_views.PasswordChangeDoneView):
    """Password change done view."""
    
    template_name = 'accounts/password_change_done.html'


class ProfileView(LoginRequiredMixin, UpdateView):
    """User profile view."""
    
    model = User
    form_class = ProfileForm
    template_name = 'accounts/profile.html'
    success_url = reverse_lazy('accounts:profile')
    
    def get_object(self):
        return self.request.user
    
    def form_valid(self, form):
        messages.success(self.request, 'Profile updated successfully.')
        return super().form_valid(form)


class UserListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    """List all users (admin only)."""
    
    model = User
    template_name = 'accounts/user_list.html'
    context_object_name = 'users'
    paginate_by = 25


class UserDetailView(LoginRequiredMixin, AdminRequiredMixin, DetailView):
    """View user details (admin only)."""
    
    model = User
    template_name = 'accounts/user_detail.html'
    context_object_name = 'user_obj'


class UserCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    """Create new user (admin only)."""
    
    model = User
    form_class = UserCreateForm
    template_name = 'accounts/user_form.html'
    success_url = reverse_lazy('accounts:user_list')
    
    def form_valid(self, form):
        messages.success(self.request, 'User created successfully.')
        return super().form_valid(form)


class UserUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    """Update user (admin only)."""
    
    model = User
    form_class = UserUpdateForm
    template_name = 'accounts/user_form.html'
    success_url = reverse_lazy('accounts:user_list')
    context_object_name = 'user_obj'
    
    def form_valid(self, form):
        messages.success(self.request, 'User updated successfully.')
        return super().form_valid(form)


class UserDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    """Delete user (admin only)."""
    
    model = User
    template_name = 'accounts/user_confirm_delete.html'
    success_url = reverse_lazy('accounts:user_list')
    context_object_name = 'user_obj'
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, 'User deleted successfully.')
        return super().delete(request, *args, **kwargs)
