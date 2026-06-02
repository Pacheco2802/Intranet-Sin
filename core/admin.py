from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, Department, LGPDConsent, AuditLog


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('icon', 'name', 'slug', 'color')
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name',)


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'get_full_name', 'email', 'role', 'is_active', 'lgpd_consent')
    list_filter = ('role', 'departments', 'is_active', 'lgpd_consent')
    search_fields = ('username', 'first_name', 'last_name', 'email')
    fieldsets = UserAdmin.fieldsets + (
        ('Informações da Intranet', {
            'fields': ('role', 'departments', 'phone', 'bio', 'avatar', 'created_by',
                       'can_post_comunicado', 'can_access_consultas')
        }),
        ('LGPD', {
            'fields': ('lgpd_consent', 'lgpd_consent_date')
        }),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Informações da Intranet', {
            'fields': ('role', 'departments', 'first_name', 'last_name', 'email')
        }),
    )


@admin.register(LGPDConsent)
class LGPDConsentAdmin(admin.ModelAdmin):
    list_display = ('user', 'policy_version', 'consent_date', 'ip_address')
    list_filter = ('policy_version',)
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('user', 'policy_version', 'consent_date', 'ip_address')


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'user', 'action', 'resource_type', 'resource_id', 'ip_address')
    list_filter = ('action', 'resource_type')
    search_fields = ('user__username', 'resource_id')
    readonly_fields = ('user', 'action', 'resource_type', 'resource_id', 'ip_address', 'timestamp', 'detail')
    date_hierarchy = 'timestamp'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
