from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from .models import User


class UserSerializer(serializers.ModelSerializer):
    """
    Serializer básico para el modelo User
    """
    full_name = serializers.SerializerMethodField()
    level_progress = serializers.SerializerMethodField()
    is_premium_active = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id', 'uuid', 'username', 'email', 'first_name', 'last_name',
            'full_name', 'bio', 'avatar', 'user_type', 'current_streak', 'longest_streak',
            'is_premium_active', 'date_joined', 'last_activity'
        ]
        read_only_fields = [
            'id', 'uuid', 'current_streak', 'longest_streak', 'date_joined', 'last_activity'
        ]
    
    def get_full_name(self, obj):
        return obj.get_full_name()
    
    def get_level_progress(self, obj):
        return obj.get_level_progress()
    
    def get_is_premium_active(self, obj):
        return obj.is_premium_active()


class UserRegistrationSerializer(serializers.ModelSerializer):
    """
    Serializer para registro de nuevos usuarios
    """
    password = serializers.CharField(write_only=True)
    password_confirm = serializers.CharField(write_only=True)
    
    class Meta:
        model = User
        fields = [
            'username', 'email', 'password', 'password_confirm',
            'first_name', 'last_name', 'user_type', 'study_level',
            'institution', 'major', 'learning_style', 'has_adhd',
            'preferred_study_time'
        ]
    
    def validate(self, attrs):
        # Verificar que las contraseñas coincidan
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError("Las contraseñas no coinciden")
        
        # Validar la contraseña usando los validadores de Django
        try:
            validate_password(attrs['password'])
        except ValidationError as e:
            raise serializers.ValidationError({'password': e.messages})
        
        return attrs
    
    def create(self, validated_data):
        # Remover password_confirm antes de crear el usuario
        validated_data.pop('password_confirm')
        
        # Crear usuario con contraseña encriptada
        user = User.objects.create_user(**validated_data)
        return user


class UserProfileSerializer(serializers.ModelSerializer):
    """
    Serializer para actualizar el perfil del usuario
    """
    full_name = serializers.SerializerMethodField(read_only=True)
    
    class Meta:
        model = User
        fields = [
            'username', 'email', 'first_name', 'last_name', 'full_name',
            'bio', 'avatar', 'birth_date', 'phone', 'user_type',
            'study_level', 'institution', 'major', 'learning_style',
            'has_adhd', 'preferred_study_time', 'timezone', 'language'
        ]
    
    def get_full_name(self, obj):
        return obj.get_full_name()
    
    def validate_email(self, value):
        """Validar que el email sea único"""
        user = self.instance
        if User.objects.exclude(pk=user.pk).filter(email=value).exists():
            raise serializers.ValidationError("Este email ya está en uso")
        return value




# class AchievementSerializer(serializers.ModelSerializer):
#     """
#     Serializer para los logros
#     """
#     class Meta:
#         model = Achievement
#         fields = ['id', 'name', 'description', 'icon', 'category', 'xp_reward']


# class UserAchievementSerializer(serializers.ModelSerializer):
#     """
#     Serializer para los logros obtenidos por el usuario
#     """
#     achievement = AchievementSerializer(read_only=True)
#     
#     class Meta:
#         model = UserAchievement
#         fields = ['id', 'achievement', 'earned_at']


class PasswordChangeSerializer(serializers.Serializer):
    """
    Serializer para cambio de contraseña
    """
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True)
    new_password_confirm = serializers.CharField(required=True)
    
    def validate_old_password(self, value):
        """Verificar que la contraseña actual sea correcta"""
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("La contraseña actual es incorrecta")
        return value
    
    def validate(self, attrs):
        """Verificar que las nuevas contraseñas coincidan"""
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError("Las nuevas contraseñas no coinciden")
        
        # Validar la nueva contraseña
        try:
            validate_password(attrs['new_password'])
        except ValidationError as e:
            raise serializers.ValidationError({'new_password': e.messages})
        
        return attrs
    
    def save(self):
        """Cambiar la contraseña del usuario"""
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save()
        return user


class UserStatsSerializer(serializers.Serializer):
    """
    Serializer para las estadísticas del usuario
    """
    total_xp = serializers.IntegerField()
    current_level = serializers.IntegerField()
    level_progress = serializers.FloatField()
    current_streak = serializers.IntegerField()
    longest_streak = serializers.IntegerField()
    total_study_time_hours = serializers.FloatField()
    tasks_completed = serializers.IntegerField()
    notes_created = serializers.IntegerField()
    achievements_earned = serializers.IntegerField()
    member_since = serializers.DateField()
    is_premium = serializers.BooleanField()
