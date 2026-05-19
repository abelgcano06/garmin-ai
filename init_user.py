from app_context import ensure_current_user_profile, get_current_user_id, get_user_profile_path

ensure_current_user_profile()

print("Usuario actual:", get_current_user_id())
print("Perfil creado en:", get_user_profile_path())