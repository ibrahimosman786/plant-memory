import { SignUp } from "@clerk/nextjs";
import { Suspense } from "react";

export default function SignUpPage() {
  return (
    <div className="flex min-h-dvh items-center justify-center bg-canvas px-4">
      <Suspense>
        <SignUp />
      </Suspense>
    </div>
  );
}
