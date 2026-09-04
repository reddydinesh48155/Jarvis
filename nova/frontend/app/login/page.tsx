import { AuthForm } from "@/components/auth-form";

export default function LoginPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-[radial-gradient(circle_at_top_left,_#e0e7ff,_transparent_40%),#f8fafc] px-5 py-12">
      <AuthForm mode="login" />
    </main>
  );
}
