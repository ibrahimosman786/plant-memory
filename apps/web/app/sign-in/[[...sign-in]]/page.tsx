import { SignIn } from "@clerk/nextjs";
import { Suspense } from "react";

export default function SignInPage() {
  return (
    <div className="flex min-h-dvh items-center justify-center bg-canvas px-4">
      <Suspense>
        <SignIn />
      </Suspense>
    </div>
  );
}
