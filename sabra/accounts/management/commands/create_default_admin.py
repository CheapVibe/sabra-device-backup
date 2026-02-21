"""
Management command to create default admin user.
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Create default admin user (admin / admin) if no users exist'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Reset admin password even if users exist',
        )
        parser.add_argument(
            '--username',
            type=str,
            default='admin',
            help='Admin username (default: admin)',
        )
        parser.add_argument(
            '--password',
            type=str,
            default='admin',
            help='Admin password (default: admin)',
        )

    def handle(self, *args, **options):
        from sabra.accounts.models import User
        
        username = options['username']
        password = options['password']
        force = options['force']
        
        if User.objects.exists() and not force:
            self.stdout.write(
                self.style.WARNING(
                    'Users already exist. Use --force to reset admin password.'
                )
            )
            return
        
        try:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'is_staff': True,
                    'is_superuser': True,
                    'is_active': True,
                    'role': User.Role.ADMIN,
                    'full_name': 'Administrator',
                    'must_change_password': True,
                }
            )
            
            if not created:
                # User exists, update to admin
                user.is_staff = True
                user.is_superuser = True
                user.is_active = True
                user.role = User.Role.ADMIN
                user.must_change_password = True
            
            user.set_password(password)
            user.save()
            
            if created:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Created default admin user: {username}'
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Reset admin user password: {username}'
                    )
                )
            
            self.stdout.write(
                self.style.WARNING(
                    'Default password is "admin" - change it immediately!'
                )
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Failed to create admin user: {e}')
            )
            raise
