import org.jetbrains.compose.desktop.application.dsl.TargetFormat

// "itor demo panel": a separate small app with the demo buttons (simulated problems).
// It reuses the itor app's code (theme, API client, panel UI) and talks to the running itor helper.
plugins {
    kotlin("jvm") version "2.1.0"
    kotlin("plugin.serialization") version "2.1.0"
    id("org.jetbrains.kotlin.plugin.compose") version "2.1.0"
    id("org.jetbrains.compose") version "1.7.3"
}

kotlin {
    jvmToolchain(17)
}

sourceSets {
    main {
        kotlin.srcDir("../desktop/src/main/kotlin")
        resources.srcDir("../desktop/src/main/resources")
    }
}

dependencies {
    implementation(compose.desktop.currentOs)
    implementation(compose.material3)
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-swing:1.9.0")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.3")
}

compose.desktop {
    application {
        mainClass = "itor.panel.PanelKt"
        nativeDistributions {
            targetFormats(TargetFormat.Msi)
            packageName = "itor demo panel"
            packageVersion = "1.0.0"
            description = "Demo buttons for itor (simulated problems)"
            vendor = "itor"
            includeAllModules = true
            windows {
                perUserInstall = true
                menuGroup = "itor"
                shortcut = true
                menu = true
                upgradeUuid = "3c1f9b52-8e4d-4a0b-9d7e-5b2a61c0f3d8"
                iconFile.set(project.file("../desktop/icons/itor.ico"))
            }
        }
    }
}
