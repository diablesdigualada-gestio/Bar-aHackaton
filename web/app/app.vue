<!-- Shell of the viewer. Owner: Carles. -->
<template>
  <UApp>
    <header class="border-b border-default">
      <UContainer class="py-4 flex items-center justify-between">
        <h1 class="text-lg font-semibold">Who has the ball?</h1>
        <div class="flex items-center gap-3">
          <span class="text-sm text-muted hidden sm:inline">Team Diables, More Than a Hack 2027</span>
          <UColorModeButton />
        </div>
      </UContainer>
    </header>
    <UContainer class="py-6">
      <NuxtPage />
    </UContainer>
  </UApp>
</template>
