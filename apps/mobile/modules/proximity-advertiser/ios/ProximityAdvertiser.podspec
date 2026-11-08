Pod::Spec.new do |s|
  s.name = 'ProximityAdvertiser'
  s.version = '0.1.0'
  s.summary = 'Foreground DeepTutor proximity pairing'
  s.description = s.summary
  s.license = 'MIT'
  s.author = 'DeepTutor'
  s.homepage = 'https://github.com/HKUDS/DeepTutor'
  s.platforms = { :ios => '15.1' }
  s.source = { :git => 'https://github.com/HKUDS/DeepTutor.git' }
  s.static_framework = true
  s.dependency 'ExpoModulesCore'
  s.frameworks = 'CoreBluetooth'
  s.source_files = '**/*.{h,m,swift}'
end
