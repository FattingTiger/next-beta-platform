plugins {
    id("com.android.application")
}

android {
    namespace = "com.company.qa.playground"
    compileSdk = 37

    defaultConfig {
        applicationId = "com.company.qa.playground"
        minSdk = 26
        targetSdk = 37
        versionCode = 1
        versionName = "1.0.0"

        testInstrumentationRunner = "android.test.InstrumentationTestRunner"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    lint {
        abortOnError = true
        checkReleaseBuilds = true
        disable += setOf("AndroidGradlePluginVersion", "ObsoleteSdkInt")
    }
}

dependencies {
    testImplementation("junit:junit:4.13.2")
}
